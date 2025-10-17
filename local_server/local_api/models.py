import uuid
from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils import timezone

class LocalMenuCache(models.Model):
    cache_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant_id = models.UUIDField()
    menu_data = JSONField()
    version = models.IntegerField(default=1)
    last_updated = models.DateTimeField(auto_now=True)
    checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # NEW: Track sync status for menu cache
    is_synced = models.BooleanField(default=True)  # Menu data is always synced from cloud
    last_sync_attempt = models.DateTimeField(blank=True, null=True)
    sync_error = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'local_menu_cache'
        indexes = [
            models.Index(fields=['restaurant_id'], name='idx_local_cache_restaurant'),
            models.Index(fields=['is_synced'], name='idx_local_cache_synced'),
        ]

class OfflineOrder(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        CANCELLED = 'cancelled', 'Cancelled'

    local_order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cloud_order_id = models.UUIDField(blank=True, null=True)
    restaurant_id = models.UUIDField()
    table_id = models.UUIDField()
    order_data = JSONField()
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    
    # ENHANCED: Improved sync tracking
    is_synced = models.BooleanField(default=False)
    sync_attempts = models.IntegerField(default=0)
    last_sync_attempt = models.DateTimeField(blank=True, null=True)
    sync_error = models.TextField(blank=True, null=True)
    sync_priority = models.IntegerField(default=1)  # 1=High, 2=Medium, 3=Low
    
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expires = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'offline_orders'
        indexes = [
            models.Index(fields=['restaurant_id'], name='idx_offline_orders_restaurant'),
            models.Index(fields=['is_synced'], name='idx_offline_orders_synced'),
            models.Index(fields=['sync_priority'], name='idx_offline_orders_priority'),
            models.Index(fields=['created_at'], name='idx_offline_orders_created'),
        ]

class SyncQueue(models.Model):
    class SyncType(models.TextChoices):
        ORDER = 'order', 'Order'
        MENU = 'menu', 'Menu'
        BOOKING = 'booking', 'Booking'
        RESTAURANT = 'restaurant', 'Restaurant'

    class SyncStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        RETRY = 'retry', 'Retry'

    sync_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sync_type = models.CharField(max_length=20, choices=SyncType.choices)
    entity_id = models.UUIDField()
    entity_data = JSONField()
    status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    last_attempt = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'sync_queue'
        indexes = [
            models.Index(fields=['sync_type', 'status'], name='idx_sync_queue_type_status'),
            models.Index(fields=['created_at'], name='idx_sync_queue_created'),
            models.Index(fields=['status', 'retry_count'], name='idx_sync_queue_retry'),
        ]

class LocalServerStatus(models.Model):
    class ServerStatus(models.TextChoices):
        ONLINE = 'online', 'Online'
        OFFLINE = 'offline', 'Offline'
        MAINTENANCE = 'maintenance', 'Maintenance'
        SYNCING = 'syncing', 'Syncing'

    server_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant_id = models.UUIDField(unique=True)
    server_name = models.CharField(max_length=255)
    server_url = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=ServerStatus.choices, default=ServerStatus.ONLINE)
    
    # NEW: Enhanced sync tracking
    last_sync = models.DateTimeField(blank=True, null=True)
    last_successful_sync = models.DateTimeField(blank=True, null=True)
    sync_status = models.CharField(max_length=20, choices=SyncQueue.SyncStatus.choices, default=SyncQueue.SyncStatus.COMPLETED)
    pending_sync_count = models.IntegerField(default=0)
    failed_sync_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'local_servers'
        indexes = [
            models.Index(fields=['status'], name='idx_local_servers_status'),
            models.Index(fields=['last_sync'], name='idx_local_servers_last_sync'),
        ]