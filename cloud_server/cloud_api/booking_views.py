from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Booking, RestaurantTable
from .booking_serializers import BookingSerializer, PreOrderBookingSerializer

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    
    def get_queryset(self):
        queryset = Booking.objects.select_related('restaurant', 'table', 'customer_user')
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create_with_preorder':
            return PreOrderBookingSerializer
        return BookingSerializer
    
    @action(detail=False, methods=['get'])
    def available_slots(self, request):
        restaurant_id = request.query_params.get('restaurant_id')
        date = request.query_params.get('date')
        party_size = int(request.query_params.get('party_size', 1))
        
        if not all([restaurant_id, date]):
            return Response({'error': 'restaurant_id and date required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get available tables for party size
        tables = RestaurantTable.objects.filter(
            restaurant_id=restaurant_id,
            capacity__gte=party_size,
            table_status='available'
        )
        
        # Generate 2-hour slots from 10 AM to 10 PM
        slots = []
        base_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        for hour in range(10, 22, 2):  # 10 AM to 10 PM, 2-hour intervals
            start_time = datetime.combine(base_date, datetime.min.time().replace(hour=hour))
            end_time = start_time + timedelta(hours=2)
            
            # Check if any table is available for this slot
            available_tables = []
            for table in tables:
                conflicting_booking = Booking.objects.filter(
                    table=table,
                    booking_date=base_date,
                    start_time__lt=end_time.time(),
                    end_time__gt=start_time.time(),
                    status__in=['confirmed', 'checked_in']
                ).exists()
                
                if not conflicting_booking:
                    available_tables.append({
                        'table_id': str(table.id),
                        'table_number': table.table_number,
                        'capacity': table.capacity
                    })
            
            if available_tables:
                slots.append({
                    'start_time': start_time.time().strftime('%H:%M'),
                    'end_time': end_time.time().strftime('%H:%M'),
                    'available_tables': available_tables
                })
        
        return Response({'available_slots': slots})
    
    @action(detail=True, methods=['post'])
    def confirm_deposit(self, request, pk=None):
        booking = self.get_object()
        payment_method = request.data.get('payment_method')
        
        if booking.deposit_status != 'pending':
            return Response({'error': 'Deposit already processed'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Simulate payment processing
        booking.deposit_status = 'paid'
        booking.status = 'confirmed'
        booking.save()
        
        return Response({
            'message': 'Deposit confirmed, booking confirmed',
            'booking_id': str(booking.id),
            'deposit_amount': str(booking.deposit_amount),
            'refund_policy': 'Deposit refundable up to 2 hours before booking time'
        })
    
    @action(detail=True, methods=['post'])
    def cancel_booking(self, request, pk=None):
        booking = self.get_object()
        
        if booking.status == 'cancelled':
            return Response({'error': 'Booking already cancelled'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check refund eligibility (2 hours before booking)
        booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
        hours_until_booking = (booking_datetime - timezone.now()).total_seconds() / 3600
        
        refund_eligible = hours_until_booking > 2
        
        booking.status = 'cancelled'
        if refund_eligible and booking.deposit_status == 'paid':
            booking.deposit_status = 'refunded'
        else:
            booking.deposit_status = 'forfeited'
        
        booking.save()
        
        return Response({
            'message': 'Booking cancelled',
            'refund_status': booking.deposit_status,
            'refund_amount': str(booking.deposit_amount) if refund_eligible else '0.00'
        })
    
    @action(detail=False, methods=['post'])
    def create_with_preorder(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        
        return Response({
            'booking': BookingSerializer(booking).data,
            'deposit_required': str(booking.deposit_amount),
            'communication_policy': {
                'deposit_policy': 'Refundable deposit required for confirmation',
                'refund_policy': 'Full refund if cancelled 2+ hours before booking',
                'no_show_policy': 'Deposit forfeited for no-shows'
            }
        }, status=status.HTTP_201_CREATED)