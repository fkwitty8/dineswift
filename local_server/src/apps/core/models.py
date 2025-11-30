import uuid
import logging
from django.db import models
from django.db.models import JSONField  # FIXED: Modern import
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.conf import settings
# Initialize logger for the model file
logger = logging.getLogger('dineswift')

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sync_version = models.IntegerField(default=0)
    
    class Meta:
        abstract = True

class Restaurant(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supabase_restaurant_id = models.UUIDField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = JSONField(default=dict)
    contact_info = JSONField(default=dict)
    local_config = JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)
    
    @property
    def has_crypto_addresses(self):
        """Quick check if the restaurant has any crypto addresses configured."""
        # Uses the reverse relationship manager 'crypto_addresses' defined on the ForeignKey
        return self.crypto_addresses.exists()
    
    
    def get_crypto_address(self, currency_code: str) -> str | None:
        """
        Retrieves the public address for a given cryptocurrency.
        Returns:
            The wallet address string, or None if not found.
        """
        try:
            
            RestaurantCryptoAddress = self.crypto_addresses.model 
            
            return self.crypto_addresses.get(currency=currency_code.upper()).address
        except RestaurantCryptoAddress.DoesNotExist:
            # Log a warning. This is expected if a restaurant hasn't set up the wallet yet.
            logger.warning(
                f"Restaurant {self.id} ({self.name}) attempted to retrieve "
                f"unconfigured crypto address for currency: {currency_code}."
            )
            return None
    
        except Exception as e:
            # Log a critical error if something went wrong outside of 'not found'
            logger.error(
                f"Unexpected error retrieving crypto address for restaurant {self.id} "
                f"and currency {currency_code}: {e}", 
                exc_info=True # Include traceback for debugging
            )
            return None
    
    # Meta and String Representation
    class Meta:
        db_table = 'restaurants'
        verbose_name = 'Restaurant'
        verbose_name_plural = 'Restaurants'
        indexes = [
            models.Index(fields=['supabase_restaurant_id', 'is_active']),
        ]
        
    def __str__(self):
        return f"{self.name}"
    

#Define Cryptocurrency Choices
# These are the crypto currencies supported by the payment gateway and to be expanded with time
CRYPTO_CURRENCY_CHOICES = [
    ('BTC', 'Bitcoin'),
    ('ETH', 'Ethereum'),
    ('SUI', 'Sui'),
    ('SOL', 'Solana'),
]

class RestaurantCryptoAddress(models.Model):
    """
    Stores the specific public wallet address for a restaurant for each supported cryptocurrency.
    This separates financial data from the core Restaurant configuration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # ForeignKey to the Restaurant model
    restaurant = models.ForeignKey(
        'core.Restaurant',
        on_delete=models.CASCADE,
        related_name='crypto_addresses',
        help_text="The restaurant that owns this wallet address."
    )
    
    # The cryptocurrency type (e.g., BTC, ETH, SUI, SOL)
    currency = models.CharField(
        max_length=5,
        choices=CRYPTO_CURRENCY_CHOICES,
        help_text="The specific cryptocurrency for this address."
    )
    
    # The public wallet address (or Lightning Invoice identifier)
    address = models.CharField(
        max_length=255,
        unique=False,
        help_text="The public wallet address for receiving funds."
    )
    
    #Additional configurations specific to the crypto network
    network_config = models.JSONField(
        default=dict,
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'restaurant_crypto_addresses'
        verbose_name = 'Restaurant Crypto Address'
        # Crucial Constraint: A restaurant can only have ONE address per currency
        unique_together = (('restaurant', 'currency'),)
        indexes = [
            models.Index(fields=['restaurant', 'currency']),
        ]
        
    def __str__(self):
        return f"{self.restaurant.name} - {self.get_currency_display()} Wallet"

class ActivityLog(TimeStampedModel):
    LOG_LEVELS = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    
    MODULES = [
        ('MENU_CACHE', 'Menu Cache'),
        ('ORDER_PROCESSING', 'Order Processing'),
        ('SYNC_MANAGER', 'Sync Manager'),
        ('OTP_SERVICE', 'OTP Service'),
        ('BILLING', 'Billing'),
        ('AUTH', 'Authentication'),
        ('CELERY', 'Celery Tasks'),
        ('PAYMENT', 'Payment Processing'),  
        ('INVOICE', 'Invoice Management'),   
        ('WALLET', 'Wallet Service'),        
        ('ACCOUNTING', 'Accounting'), 
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(
        Restaurant, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    level = models.CharField(max_length=10, choices=LOG_LEVELS, db_index=True)
    module = models.CharField(max_length=20, choices=MODULES, db_index=True)
    action = models.CharField(max_length=100)
    details = JSONField(default=dict)
    user = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.SET_NULL,
            null=True,
            blank=True
            )
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'activity_logs'
        indexes = [
            models.Index(fields=['restaurant', '-created_at']),
            models.Index(fields=['module', 'level', '-created_at']),
            models.Index(fields=['correlation_id']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_level_display()} - {self.module} - {self.action}"

class SyncQueue(TimeStampedModel):
    SYNC_TYPES = [
        ('ORDER_CREATE', 'Order Create'),
        ('ORDER_UPDATE', 'Order Update'),
        ('ORDER_DELETE', 'Order Delete'),
        ('MENU_UPDATE', 'Menu Update'),
        ('INVENTORY_UPDATE', 'Inventory Update'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CONFLICT', 'Conflict'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPES, db_index=True)
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING',
        db_index=True
    )
    priority = models.IntegerField(default=5)  # 1=highest, 10=lowest
    payload = JSONField()
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    supabase_id = models.UUIDField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=5)
    last_retry = models.DateTimeField(null=True, blank=True)
    next_retry = models.DateTimeField(null=True, blank=True, db_index=True)
    error_message = models.TextField(blank=True)
    conflict_data = JSONField(null=True, blank=True)
    
    class Meta:
        db_table = 'sync_queue'
        indexes = [
            models.Index(fields=['restaurant', 'status', 'priority', 'created_at']),
            models.Index(fields=['status', 'next_retry']),
            models.Index(fields=['idempotency_key']),
        ]
        ordering = ['priority', 'created_at']
    
    def __str__(self):
        return f"{self.sync_type} - {self.status}"
    
    def can_retry(self):
        return self.retry_count < self.max_retries and self.status == 'FAILED'
    
    def mark_retry(self, error_msg=''):
        from datetime import timedelta
        self.retry_count += 1
        self.last_retry = timezone.now()
        # Exponential backoff
        delay = min(2 ** self.retry_count * 60, 3600)  # Max 1 hour
        self.next_retry = timezone.now() + timedelta(seconds=delay)
        self.error_message = error_msg[:1000]
        if not self.can_retry():
            self.status = 'FAILED'
        self.save()

class HealthCheck(models.Model):
    COMPONENT_CHOICES = [
        ('DATABASE', 'Database'),
        ('REDIS', 'Redis'),
        ('SUPABASE', 'Supabase'),
        ('CELERY', 'Celery'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    component = models.CharField(max_length=20, choices=COMPONENT_CHOICES)
    is_healthy = models.BooleanField(default=True)
    response_time_ms = models.IntegerField(null=True)
    last_check = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'health_checks'
        indexes = [
            models.Index(fields=['component', '-last_check']),
        ]

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(
        Restaurant, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='users'
    )

    # Add custom fields here if needed

    def __str__(self):
        return self.username