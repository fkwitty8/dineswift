from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from .serializers import OrderSerializer, MenuItemSerializer, BookingSerializer, PaymentSerializer, SupplierSerializer, RestaurantSupplierSerializer, SupplyOrderSerializer
from .models import RestaurantTable, MenuItem, Booking, Order, Supplier, RestaurantSupplier, SupplyOrder, Restaurant
from .payment_service import MoMoPaymentService


def api_home(request):
    return JsonResponse({
        'message': 'DineSwift Cloud API',
        'endpoints': {
            'orders': '/api/orders/',
            'qr_resolve': '/api/qr/<qr_code>/',
            'bookings': '/api/bookings/',
            'payments': '/api/payments/',
            'checkin': '/api/checkin/<ticket_qr>/'
        }
    })


@api_view(['POST'])
def create_order(request):
    serializer = OrderSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def resolve_qr_code(request, qr_code):
    try:
        table = RestaurantTable.objects.select_related('restaurant').get(qr_code=qr_code)
        menu_items = MenuItem.objects.filter(
            menu__restaurant=table.restaurant,
            is_available=True
        ).order_by('display_order')
        
        return Response({
            'restaurant_id': table.restaurant.id,
            'restaurant_name': table.restaurant.name,
            'table_id': table.id,
            'table_number': table.table_number,
            'menu_items': MenuItemSerializer(menu_items, many=True).data
        })
    except RestaurantTable.DoesNotExist:
        return Response({'error': 'Invalid QR code'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def create_booking(request):
    serializer = BookingSerializer(data=request.data)
    if serializer.is_valid():
        booking = serializer.save(status='pending', deposit_status='pending')
        ticket_qr = f"TICKET-{booking.id}"
        return Response({
            **serializer.data,
            'ticket_qr_code': ticket_qr,
            'booking_id': booking.id
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def confirm_booking_payment(request, booking_id):
    try:
        booking = Booking.objects.get(id=booking_id)
        booking.deposit_status = 'paid'
        booking.status = 'confirmed'
        booking.save()
        return Response({'message': 'Booking confirmed', 'booking_id': booking_id})
    except Booking.DoesNotExist:
        return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def process_payment(request):
    serializer = PaymentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    service = MoMoPaymentService()
    
    payment = service.initiate_payment(
        idempotency_key=data['idempotency_key'],
        amount=data['amount'],
        phone_number=data['phone_number'],
        payment_type=data['payment_type'],
        reference_id=data['reference_id']
    )
    
    if payment.status == 'completed':
        if payment.payment_type == 'order':
            Order.objects.filter(id=payment.reference_id).update(status='confirmed')
        elif payment.payment_type == 'booking':
            Booking.objects.filter(id=payment.reference_id).update(
                deposit_status='paid', status='confirmed'
            )
    
    return Response({
        'payment_id': payment.id,
        'status': payment.status,
        'transaction_id': payment.momo_transaction_id
    }, status=status.HTTP_201_CREATED if payment.status == 'completed' else status.HTTP_200_OK)


@api_view(['POST'])
def checkin_booking(request, ticket_qr):
    try:
        booking_id = ticket_qr.replace('TICKET-', '')
        booking = Booking.objects.select_related('restaurant', 'customer_user', 'table').get(id=booking_id)
        
        if booking.status != 'confirmed':
            return Response({'error': 'Booking not confirmed'}, status=status.HTTP_400_BAD_REQUEST)
        
        booking.status = 'checked_in'
        booking.save()
        
        return Response({
            'message': 'Check-in successful',
            'booking_id': booking.id,
            'customer_name': booking.customer_user.get_full_name(),
            'table_number': booking.table.table_number,
            'party_size': booking.party_size,
            'staff_notified': True
        })
    except Booking.DoesNotExist:
        return Response({'error': 'Invalid ticket'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET', 'POST'])
def supplier_list(request):
    if request.method == 'GET':
        suppliers = Supplier.objects.filter(is_active=True)
        serializer = SupplierSerializer(suppliers, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = SupplierSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def supplier_detail(request, supplier_id):
    try:
        supplier = Supplier.objects.get(id=supplier_id)
    except Supplier.DoesNotExist:
        return Response({'error': 'Supplier not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = SupplierSerializer(supplier)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = SupplierSerializer(supplier, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        supplier.is_active = False
        supplier.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
def restaurant_supplier_list(request, restaurant_id):
    if request.method == 'GET':
        relationships = RestaurantSupplier.objects.filter(
            restaurant_id=restaurant_id
        ).select_related('supplier')
        serializer = RestaurantSupplierSerializer(relationships, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        data = request.data.copy()
        data['restaurant'] = restaurant_id
        serializer = RestaurantSupplierSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
def restaurant_supplier_detail(request, restaurant_id, relationship_id):
    try:
        relationship = RestaurantSupplier.objects.get(
            id=relationship_id, restaurant_id=restaurant_id
        )
    except RestaurantSupplier.DoesNotExist:
        return Response({'error': 'Relationship not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'PUT':
        serializer = RestaurantSupplierSerializer(relationship, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        relationship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def create_supply_order(request, restaurant_id):
    try:
        restaurant = Restaurant.objects.get(id=restaurant_id)
    except Restaurant.DoesNotExist:
        return Response({'error': 'Restaurant not found'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = SupplyOrderSerializer(data=request.data, context={'restaurant': restaurant})
    if serializer.is_valid():
        supply_order = serializer.save()
        return Response({
            'supply_order_id': supply_order.id,
            'order_id': supply_order.order.id,
            'supplier_id': supply_order.supplier.id,
            'status': supply_order.order.status,
            'expected_delivery_date': supply_order.expected_delivery_date
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
