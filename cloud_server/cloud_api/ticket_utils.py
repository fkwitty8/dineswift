import hashlib
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta
from django.utils import timezone
from .models import DigitalTicket, Order

def generate_ticket_qr_code(order_id):
    """Generate unique QR code for order ticket"""
    timestamp = str(int(timezone.now().timestamp()))
    data = f"{order_id}_{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]

def create_qr_code_image(qr_data):
    """Generate QR code image as base64 string"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def generate_digital_ticket(order):
    """Generate digital ticket for order"""
    qr_code = generate_ticket_qr_code(order.id)
    expires_at = timezone.now() + timedelta(hours=24)  # Ticket expires in 24 hours
    
    ticket = DigitalTicket.objects.create(
        order=order,
        qr_code=qr_code,
        expires_at=expires_at
    )
    
    return ticket

def validate_ticket_qr(qr_code):
    """Validate QR code and return ticket if valid"""
    try:
        ticket = DigitalTicket.objects.select_related('order', 'order__restaurant').get(
            qr_code=qr_code,
            ticket_status='active'
        )
        
        if ticket.expires_at < timezone.now():
            ticket.ticket_status = 'expired'
            ticket.save()
            return None, 'Ticket expired'
        
        return ticket, 'Valid'
    except DigitalTicket.DoesNotExist:
        return None, 'Invalid QR code'