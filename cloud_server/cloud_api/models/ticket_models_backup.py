import uuid
from django.db import models
from .models import Order, User, Restaurant

class DigitalTicket(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    ticket_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='ticket')
    qr_code = models.CharField(max_length=500, unique=True)
    ticket_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    check_in_time = models.DateTimeField(blank=True, null=True)
    checked_in_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'digital_tickets'
        indexes = [
            models.Index(fields=['qr_code'], name='idx_tickets_qr_code'),
            models.Index(fields=['ticket_status'], name='idx_tickets_status'),
            models.Index(fields=['expires_at'], name='idx_tickets_expires'),
        ]