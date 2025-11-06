import uuid
from django.db import models
from django.db.models import JSONField
from apps.core.models import TimeStampedModel


class Payment(TimeStampedModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    GATEWAY_CHOICES = [
        ('MOMO', 'Mobile Money'),
        ('VISA', 'Visa'),
        ('MASTERCARD', 'Mastercard'),
        ('CASH', 'Cash'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        'order_processing.OfflineOrder', 
        on_delete=models.CASCADE,
        related_name='payments'
    )
    restaurant = models.ForeignKey('core.Restaurant', on_delete=models.CASCADE)
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='UGX')
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Gateway references
    gateway_reference = models.CharField(max_length=255, blank=True, null=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Customer information
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    
    # Timing
    processed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Error handling
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    
        
    class Meta:
        db_table = 'payments'
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['restaurant', 'status']),
            models.Index(fields=['gateway_reference']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment {self.id} - {self.get_status_display()}"
    
    def mark_processing(self):
        self.status = 'PROCESSING'
        self.save()
    
    def mark_completed(self, gateway_reference=None, response_data=None):
        self.status = 'COMPLETED'
        self.gateway_reference = gateway_reference
        self.gateway_response = response_data or {}
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message):
        self.status = 'FAILED'
        self.error_message = error_message
        self.retry_count += 1
        self.save()