from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import DigitalTicket, Order, Notification, User
from .ticket_utils import generate_digital_ticket, validate_ticket_qr, create_qr_code_image

@api_view(['POST'])
def generate_ticket(request):
    """Generate digital ticket for order"""
    order_id = request.data.get('order_id')
    
    if not order_id:
        return Response({'error': 'order_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        order = Order.objects.select_related('restaurant').get(id=order_id)
        
        # Check if ticket already exists
        if hasattr(order, 'ticket'):
            ticket = order.ticket
        else:
            ticket = generate_digital_ticket(order)
        
        # Generate QR code image
        qr_image = create_qr_code_image(ticket.qr_code)
        
        # Notify staff
        _notify_staff_new_order(order, ticket)
        
        return Response({
            'ticket_id': str(ticket.ticket_id),
            'qr_code': ticket.qr_code,
            'qr_image': qr_image,
            'order_id': str(order.id),
            'restaurant_name': order.restaurant.name,
            'expires_at': ticket.expires_at,
            'status': ticket.ticket_status,
            'check_in_url': f'/api/tickets/checkin/{ticket.qr_code}/'
        })
        
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
def checkin_ticket(request, qr_code):
    """Check in customer using QR code"""
    staff_user_id = request.data.get('staff_user_id')
    
    ticket, message = validate_ticket_qr(qr_code)
    
    if not ticket:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
    
    if ticket.ticket_status == 'used':
        return Response({
            'error': 'Ticket already used',
            'check_in_time': ticket.check_in_time
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Process check-in
    ticket.ticket_status = 'used'
    ticket.check_in_time = timezone.now()
    
    if staff_user_id:
        try:
            staff_user = User.objects.get(id=staff_user_id)
            ticket.checked_in_by = staff_user
        except User.DoesNotExist:
            pass
    
    ticket.save()
    
    # Update order status
    order = ticket.order
    if order.status == 'confirmed':
        order.status = 'preparing'
        order.save()
    
    return Response({
        'message': 'Check-in successful',
        'ticket_id': str(ticket.ticket_id),
        'order_id': str(order.id),
        'customer_name': order.salesorder.customer_user.username if hasattr(order, 'salesorder') else 'Customer',
        'table_number': order.salesorder.table.table_number if hasattr(order, 'salesorder') and order.salesorder.table else None,
        'check_in_time': ticket.check_in_time,
        'order_total': str(order.total_amount)
    })

@api_view(['GET'])
def ticket_status(request, qr_code):
    """Get ticket status"""
    ticket, message = validate_ticket_qr(qr_code)
    
    if not ticket:
        return Response({'error': message}, status=status.HTTP_404_NOT_FOUND)
    
    return Response({
        'ticket_id': str(ticket.ticket_id),
        'status': ticket.ticket_status,
        'order_id': str(ticket.order.id),
        'expires_at': ticket.expires_at,
        'check_in_time': ticket.check_in_time,
        'checked_in_by': ticket.checked_in_by.username if ticket.checked_in_by else None
    })

def _notify_staff_new_order(order, ticket):
    """Send notification to restaurant staff about new order"""
    try:
        # Get restaurant staff (simplified - would normally filter by role/shift)
        staff_users = User.objects.filter(
            userrole__restaurant=order.restaurant,
            userrole__is_active=True
        )[:5]  # Limit to 5 staff members
        
        for staff_user in staff_users:
            Notification.objects.create(
                recipient=staff_user,
                source_entity_id=order.id,
                source_entity_type='order',
                notification_type='order_update',
                message=f'New order #{str(order.id)[:8]} - Digital ticket generated. QR: {ticket.qr_code[:8]}...',
                action_url=f'/api/tickets/checkin/{ticket.qr_code}/'
            )
    except Exception:
        pass  # Fail silently if notification fails