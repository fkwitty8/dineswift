import uuid
from django.db import models
from django.db.models import JSONField
from apps.core.models import TimeStampedModel, Restaurant

class OfflineOrder(TimeStampedModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('PREPARING', 'Preparing'),
        ('READY', 'Ready'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    SYNC_STATUS_CHOICES = [
        ('PENDING_SYNC', 'Pending Sync'),
        ('SYNCING', 'Syncing'),
        ('SYNCED', 'Synced'),
        ('SYNC_FAILED', 'Sync Failed'),
        ('CONFLICT', 'Conflict'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    local_order_id = models.CharField(max_length=50, unique=True)  # Human-readable ID
    supabase_order_id = models.UUIDField(null=True, blank=True)
    
    # Order details
    table_id = models.UUIDField(null=True, blank=True)
    customer_id = models.UUIDField(null=True, blank=True)
    order_items = JSONField()  # List of order items with details
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    special_instructions = models.TextField(blank=True)
    
    # Status tracking
    order_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    sync_status = models.CharField(max_length=20, choices=SYNC_STATUS_CHOICES, default='PENDING_SYNC')
    
    # Timing
    estimated_preparation_time = models.IntegerField(null=True, blank=True)  # in minutes
    actual_preparation_time = models.IntegerField(null=True, blank=True)
    preparation_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Sync information
    sync_attempts = models.IntegerField(default=0)
    last_sync_attempt = models.DateTimeField(null=True, blank=True)
    sync_error = models.TextField(blank=True)
    
    payment = models.ForeignKey(
        'payment.Payment', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='orders'
    )
    
    class Meta:
        db_table = 'offline_orders'
        indexes = [
            models.Index(fields=['restaurant', 'order_status']),
            models.Index(fields=['restaurant', 'sync_status']),
            models.Index(fields=['local_order_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Order {self.local_order_id} - {self.get_order_status_display()}"

class OrderCRDTState(TimeStampedModel):
    """CRDT state for conflict resolution"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(OfflineOrder, on_delete=models.CASCADE)
    vector_clock = JSONField()  # {node_id: counter}
    last_operation = models.CharField(max_length=50)
    operation_timestamp = models.DateTimeField()
    
    class Meta:
        db_table = 'order_crdt_states'
        
    def __str__(self):
        return f"CRDT State for {self.order.local_order_id}"