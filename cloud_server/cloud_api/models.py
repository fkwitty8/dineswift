import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import JSONField

class User(AbstractUser):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    gps_location = JSONField(blank=True, null=True)
    communication_preferences = JSONField(default={
        "email_notifications": True,
        "sms_notifications": True, 
        "push_notifications": True
    })
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        db_table = 'users'

class Restaurant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'

    class HalalStatus(models.TextChoices):
        HALAL = 'halal', 'Halal Certified'
        NOT_HALAL = 'not_halal', 'Not Halal'
        HALAL_OPTIONS = 'halal_options', 'Halal Options Available'
        UNKNOWN = 'unknown', 'Unknown'

    restaurant_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    cuisine_type = models.CharField(max_length=100, blank=True, null=True)
    
    # NEW: Logo field for restaurant branding
    logo = models.ImageField(upload_to='restaurant_logos/', blank=True, null=True)
    logo_url = models.URLField(blank=True, null=True)  # Alternative if using external URLs
    
    # NEW: Halal status for Muslim customers
    halal_status = models.CharField(
        max_length=20, 
        choices=HalalStatus.choices, 
        default=HalalStatus.UNKNOWN
    )
    halal_certification_number = models.CharField(max_length=100, blank=True, null=True)
    halal_certification_authority = models.CharField(max_length=255, blank=True, null=True)
    
    address = JSONField()
    contact_info = JSONField()
    operation_hours = JSONField()
    social_media_links = JSONField(blank=True, null=True)
    delivery_options = JSONField(blank=True, null=True)
    payment_methods_accepted = JSONField(blank=True, null=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    average_delivery_time = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    local_server_id = models.UUIDField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_restaurants')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_restaurants')
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='deleted_restaurants')

    class Meta:
        db_table = 'restaurants'
        indexes = [
            models.Index(fields=['status'], name='idx_restaurants_status'),
            models.Index(fields=['cuisine_type'], name='idx_restaurants_cuisine'),
            models.Index(fields=['average_rating'], name='idx_restaurants_rating'),
            models.Index(fields=['created_at'], name='idx_restaurants_created_at'),
            # NEW: Index for halal status filtering
            models.Index(fields=['halal_status'], name='idx_restaurants_halal_status'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_halal_status_display()})"

class RestaurantTable(models.Model):
    class TableStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        OCCUPIED = 'occupied', 'Occupied'
        RESERVED = 'reserved', 'Reserved'
        MAINTENANCE = 'maintenance', 'Maintenance'

    table_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    table_number = models.CharField(max_length=20)
    qr_code = models.CharField(max_length=500, unique=True)
    capacity = models.IntegerField()
    table_status = models.CharField(max_length=20, choices=TableStatus.choices, default=TableStatus.AVAILABLE)
    coordinates = JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'restaurant_tables'

class Menu(models.Model):
    menu_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menus'

class MenuItem(models.Model):
    class DietaryCategory(models.TextChoices):
        VEGETARIAN = 'vegetarian', 'Vegetarian'
        VEGAN = 'vegan', 'Vegan'
        GLUTEN_FREE = 'gluten_free', 'Gluten Free'
        DAIRY_FREE = 'dairy_free', 'Dairy Free'
        NUT_FREE = 'nut_free', 'Nut Free'
        HALAL = 'halal', 'Halal'
        KOSHER = 'kosher', 'Kosher'

    menu_item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    sales_price = models.DecimalField(max_digits=10, decimal_places=2)
    preparation_time = models.IntegerField()
    department = models.CharField(max_length=100, blank=True, null=True)
    
    # NEW: Dietary information for menu items
    dietary_categories = models.JSONField(default=list, blank=True)  # Stores list of DietaryCategory choices
    is_halal = models.BooleanField(default=False)
    halal_certified = models.BooleanField(default=False)
    
    is_available = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menu_items'
        indexes = [
            # NEW: Index for dietary filtering
            models.Index(fields=['is_halal'], name='idx_menu_items_halal'),
            models.Index(fields=['dietary_categories'], name='idx_menu_items_dietary'),
        ]

class Order(models.Model):
    class OrderType(models.TextChoices):
        SALES = 'sales', 'Sales'
        SUPPLY = 'supply', 'Supply'

    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        IN_DELIVERY = 'in_delivery', 'In Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    status = models.CharField(max_length=50, choices=OrderStatus.choices)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_orders')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_orders')

    class Meta:
        db_table = 'orders'

class SalesOrder(models.Model):
    class OrderSubtype(models.TextChoices):
        DINE_IN = 'dine_in', 'Dine In'
        TAKEAWAY = 'takeaway', 'Takeaway'
        DELIVERY = 'delivery', 'Delivery'

    sales_order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    customer_user = models.ForeignKey(User, on_delete=models.CASCADE)
    order_subtype = models.CharField(max_length=20, choices=OrderSubtype.choices)
    table = models.ForeignKey(RestaurantTable, on_delete=models.SET_NULL, null=True)
    assigned_waiter_id = models.UUIDField(blank=True, null=True)
    batch_id = models.UUIDField(blank=True, null=True)
    delivery_partner_id = models.UUIDField(blank=True, null=True)
    customer_coordinates = JSONField(blank=True, null=True)
    estimated_preparation_time = models.IntegerField(blank=True, null=True)
    actual_preparation_time = models.IntegerField(blank=True, null=True)
    estimated_delivery_time = models.IntegerField(blank=True, null=True)
    actual_delivery_time = models.IntegerField(blank=True, null=True)
    preparation_complexity_score = models.IntegerField(blank=True, null=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

    class Meta:
        db_table = 'sales_orders'

class OrderItem(models.Model):
    class SourceEntityType(models.TextChoices):
        MENU_ITEM = 'menu_item', 'Menu Item'
        INVENTORY_ITEM = 'inventory_item', 'Inventory Item'

    order_item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    source_entity_id = models.UUIDField()
    source_entity_type = models.CharField(max_length=20, choices=SourceEntityType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    special_instructions = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    item_notes = models.TextField(blank=True, null=True)
    customization_options = JSONField(blank=True, null=True)
    chef_special_instructions = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'order_items'

class Booking(models.Model):
    class BookingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        CHECKED_IN = 'checked_in', 'Checked In'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        NO_SHOW = 'no_show', 'No Show'

    class DepositStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        REFUNDED = 'refunded', 'Refunded'
        FORFEITED = 'forfeited', 'Forfeited'

    booking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_user = models.ForeignKey(User, on_delete=models.CASCADE)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    table = models.ForeignKey(RestaurantTable, on_delete=models.CASCADE)
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    party_size = models.IntegerField()
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_status = models.CharField(max_length=20, choices=DepositStatus.choices, default=DepositStatus.PENDING)
    special_requests = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bookings'