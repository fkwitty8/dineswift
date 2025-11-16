import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.indexes import GinIndex, BTreeIndex
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils.translation import gettext_lazy as _


def get_default_communication_preferences():
    return {
        'email_notifications': True,
        'sms_notifications': True, 
        'push_notifications': True
    }


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    gps_location = models.JSONField(blank=True, null=True)
    
    communication_preferences = models.JSONField(
        default=get_default_communication_preferences 
    )
     
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(blank=True, null=True)
    # 1. Redefine 'groups' to fix clash with auth.User
    groups = models.ManyToManyField(
        Group,
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to.'
        ),
        related_name='api_user_groups', # <-- REQUIRED UNIQUE NAME
        related_query_name='api_user',
    )
    
    # 2. Redefine 'user_permissions' to fix clash with auth.User
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name='api_user_permissions', # <-- REQUIRED UNIQUE NAME
        related_query_name='api_user',
    )
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email'], name='idx_users_email'),
            models.Index(fields=['is_active'], name='idx_users_active', condition=Q(is_active=True)),
            models.Index(fields=['last_login'], name='idx_users_last_login'),
            GinIndex(fields=['communication_preferences'], name='idx_users_communication_prefs'),
        ]

class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role_name = models.CharField(max_length=50, unique=True)
    permissions = models.JSONField()
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    class Meta:
        db_table = 'roles'
        indexes = [
            models.Index(fields=['role_name'], name='idx_roles_name'),
        ]

class Restaurant(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    cuisine_type = models.CharField(max_length=100, blank=True, null=True)
    address = models.JSONField()
    contact_info = models.JSONField()
    operation_hours = models.JSONField()
    social_media_links = models.JSONField(blank=True, null=True)
    delivery_options = models.JSONField(blank=True, null=True)
    payment_methods_accepted = models.JSONField(blank=True, null=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.IntegerField(default=0)
    average_delivery_time = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurants'
        indexes = [
            models.Index(fields=['status'], name='idx_restaurants_status'),
            models.Index(fields=['cuisine_type'], name='idx_restaurants_cuisine'),
            models.Index(fields=['average_rating'], name='idx_restaurants_rating'),
            models.Index(fields=['created_at'], name='idx_restaurants_created_at'),
        ]

class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'user_roles'
        indexes = [
            models.Index(fields=['user'], name='idx_user_roles_user'),
            models.Index(fields=['restaurant'], name='idx_user_roles_restaurant'),
            models.Index(fields=['user', 'role', 'restaurant'], name='idx_user_roles_active', condition=Q(is_active=True)),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'role', 'restaurant'],
                condition=Q(is_active=True),
                name='idx_user_role_unique'
            )
        ]

class RestaurantTable(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('reserved', 'Reserved'),
        ('maintenance', 'Maintenance'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    table_number = models.CharField(max_length=20)
    qr_code = models.CharField(max_length=500, unique=True)
    capacity = models.IntegerField(validators=[MinValueValidator(1)])
    table_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    coordinates = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_tables'
        indexes = [
            models.Index(fields=['restaurant'], name='idx_tables_restaurant'),
            models.Index(fields=['table_status'], name='idx_tables_status'),
            models.Index(fields=['capacity'], name='idx_tables_capacity'),
            models.Index(fields=['restaurant', 'table_status'], name='idx_tables_restaurant_status'),
            models.Index(fields=['qr_code'], name='idx_tables_qr_code'),
        ]

class LocalServer(models.Model):
    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('maintenance', 'Maintenance'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.OneToOneField(Restaurant, on_delete=models.CASCADE)
    server_name = models.CharField(max_length=255, blank=True, null=True)
    server_url = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='online')
    last_sync = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'local_servers'
        indexes = [
            models.Index(fields=['status'], name='idx_local_servers_status'),
            models.Index(fields=['last_sync'], name='idx_local_servers_last_sync'),
        ]

class Menu(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.OneToOneField(Restaurant, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menus'
        indexes = [
            models.Index(fields=['restaurant'], name='idx_menus_restaurant_active', condition=Q(is_active=True)),
            models.Index(fields=['is_active'], name='idx_menus_active'),
        ]

class MenuItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    sales_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    preparation_time = models.IntegerField(validators=[MinValueValidator(1)])
    department = models.CharField(max_length=100, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    image = models.ImageField(
        upload_to='menu_items/',
        null=True,
        blank=True,
        verbose_name='Item Image'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_items'
        indexes = [
            models.Index(fields=['menu'], name='idx_menu_items_menu'),
            models.Index(fields=['is_available'], name='idx_menu_items_available'),
            models.Index(fields=['sales_price'], name='idx_menu_items_price'),
            models.Index(fields=['preparation_time'], name='idx_menu_items_prep_time'),
            models.Index(fields=['department'], name='idx_menu_items_department'),
            models.Index(fields=['menu', 'is_available', 'display_order'], name='idx_menu_item_avilable'),
            models.Index(fields=['menu', 'sales_price'], name='idx_menu_items_active_price', condition=Q(is_available=True)),
        ]

class InventoryItem(models.Model):
    STATUS_CHOICES = [
        ('in_stock', 'In Stock'),
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    unit_of_measure = models.CharField(max_length=50)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], blank=True, null=True)
    current_stock = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    min_stock_threshold = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    max_stock_capacity = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    stock_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_stock')
    last_restocked = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_items'
        indexes = [
            models.Index(fields=['restaurant'], name='idx_inventory_restaurant'),
            models.Index(fields=['stock_status'], name='idx_inventory_status'),
            models.Index(fields=['restaurant', 'stock_status'], name='idx_inventory_low_stock', condition=Q(stock_status__in=['low_stock', 'out_of_stock'])),
        ]

class MenuItemIngredient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity_required = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_item_ingredients'
        constraints = [
            models.UniqueConstraint(fields=['menu_item', 'inventory_item'], name='unique_menu_item_ingredient')
        ]
        indexes = [
            models.Index(fields=['menu_item'], name='idx_ingredients_menu_item'),
            models.Index(fields=['inventory_item'], name='idx_ingredients_inventory_item'),
        ]

class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    contact_info = models.JSONField()
    address = models.JSONField(blank=True, null=True)
    business_registration = models.CharField(max_length=100, blank=True, null=True)
    payment_terms = models.JSONField(blank=True, null=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'suppliers'
        indexes = [
            models.Index(fields=['is_active'], name='idx_suppliers_active'),
            models.Index(fields=['rating'], name='idx_suppliers_rating'),
        ]

class RestaurantSupplier(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    relationship_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_preferred = models.BooleanField(default=False)
    payment_terms = models.JSONField(blank=True, null=True)
    delivery_lead_time = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'restaurant_suppliers'
        constraints = [
            models.UniqueConstraint(fields=['restaurant', 'supplier'], name='unique_restaurant_supplier')
        ]
        indexes = [
            models.Index(fields=['restaurant'], name='idx_rs_restaurant'),
            models.Index(fields=['supplier'], name='idx_rs_supplier'),
            models.Index(fields=['relationship_status'], name='idx_rs_status'),
            models.Index(fields=['restaurant', 'is_preferred'], name='idx_rs_preferred', condition=Q(is_preferred=True)),
        ]

class DeliveryBatch(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    assigned_waiter = models.ForeignKey(User, on_delete=models.CASCADE)
    batch_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    optimized_route = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    total_distance = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    estimated_completion_time = models.IntegerField(blank=True, null=True)
    actual_completion_time = models.IntegerField(blank=True, null=True)
    fuel_cost_estimate = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    batch_efficiency_score = models.DecimalField(max_digits=4, decimal_places=2, default=0.00)
    
    class Meta:
        db_table = 'delivery_batches'
        indexes = [
            models.Index(fields=['restaurant'], name='idx_dv_restaurant'),
            models.Index(fields=['batch_status'], name='idx_dv_status'),
            models.Index(fields=['assigned_waiter'], name='idx_dv_waiter'),
            models.Index(fields=['created_at'], name='idx_dv_created_at'),
            models.Index(fields=['batch_efficiency_score'], name='idx_dv_efficiency'),
            models.Index(fields=['total_distance'], name='idx_dv_distance'),
            models.Index(fields=['estimated_completion_time', 'actual_completion_time'], name='idx_dv_completion'),
        ]

class KitchenDisplayOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('served', 'Served'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey('Order', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    special_instructions = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    station_assigned = models.CharField(max_length=100, blank=True, null=True)
    preparation_start_time = models.DateTimeField(blank=True, null=True)
    preparation_end_time = models.DateTimeField(blank=True, null=True)
    chef_notes = models.TextField(blank=True, null=True)
    priority = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kitchen_display_orders'
        indexes = [
            models.Index(fields=['status'], name='idx_ko_status'),
            models.Index(fields=['station_assigned'], name='idx_ko_station'),
            models.Index(fields=['priority', 'created_at'], name='idx_ko_priority'),
            models.Index(fields=['preparation_start_time', 'preparation_end_time'], name='idx_ko_preparation'),
        ]

class Order(models.Model):
    TYPE_CHOICES = [
        ('sales', 'Sales'),
        ('supply', 'Supply'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('in_delivery', 'In Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    order_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'order'
        indexes = [
            models.Index(fields=['restaurant', 'created_at'], name='idx_orders_restaurant_created'),
            models.Index(fields=['status', 'created_at'], name='idx_orders_status_created'),
            models.Index(fields=['created_at'], name='idx_orders_created_at'),
            models.Index(fields=['restaurant', 'created_at'], name='idx_orders_active', condition=~models.Q(status__in=['cancelled', 'delivered'])),
            models.Index(fields=['restaurant', 'status', 'created_at'], name='idx_orders_kitchen_status', condition=models.Q(status__in=['confirmed', 'preparing'])),
        ]

class SalesOrder(models.Model):
    SUBTYPE_CHOICES = [
        ('dine_in', 'Dine In'),
        ('takeaway', 'Takeaway'),
        ('delivery', 'Delivery'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    customer_user = models.ForeignKey(User, on_delete=models.CASCADE)
    order_subtype = models.CharField(max_length=20, choices=SUBTYPE_CHOICES)
    table = models.ForeignKey(RestaurantTable, on_delete=models.SET_NULL, blank=True, null=True)
    assigned_waiter = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='assigned_orders')
    estimated_preparation_time = models.IntegerField(blank=True, null=True)
    actual_preparation_time = models.IntegerField(blank=True, null=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)      
        
    class Meta:
        db_table = 'sales_orders'
        indexes = [
            models.Index(fields=['customer_user'], name='idx_sales_orders_customer'),
            models.Index(fields=['order_subtype'], name='idx_sales_orders_subtype'),
            models.Index(fields=['table'], name='idx_sales_orders_table'),
            models.Index(fields=['assigned_waiter'], name='idx_sales_orders_waiter'),
            models.Index(fields=['customer_user', 'created_at'], name='idx_sales_orders_customer_date'),
        ]

class OrderItem(models.Model):
    SOURCE_CHOICES = [
        ('menu_item', 'Menu Item'),
        ('inventory_item', 'Inventory Item'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    source_entity_id = models.UUIDField()
    source_entity_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    total_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    special_instructions = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True) 
    updated_at = models.DateTimeField(auto_now=True) 
    
    class Meta:
        db_table = 'order_items'
        indexes = [
            models.Index(fields=['order'], name='idx_order_items_order'),
            models.Index(fields=['source_entity_id', 'source_entity_type'], name='idx_order_items_source_entity'),
            models.Index(fields=['source_entity_type', 'source_entity_id'], name='idx_order_items_source_type'),
        ]

class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    DEPOSIT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('forfeited', 'Forfeited'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_user = models.ForeignKey(User, on_delete=models.CASCADE)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    table = models.ForeignKey(RestaurantTable, on_delete=models.CASCADE)
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    party_size = models.IntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    deposit_status = models.CharField(max_length=20, choices=DEPOSIT_STATUS_CHOICES, default='pending')
    special_requests = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  
    current_date = models.DateField(auto_now=True)
    
    class Meta:
        db_table = 'bookings'
        indexes = [
            models.Index(fields=['restaurant'], name='idx_bookings_restaurant'),
            models.Index(fields=['customer_user'], name='idx_bookings_customer'),
            models.Index(fields=['table'], name='idx_bookings_table'),
            models.Index(fields=['booking_date'], name='idx_bookings_date'),
            models.Index(fields=['status'], name='idx_bookings_status'),
            models.Index(fields=['restaurant', 'booking_date'], name='idx_bookings_restaurant_date'),
            models.Index(fields=['customer_user', 'booking_date'], name='idx_bookings_customer_date'),
        ]

class OrderItemRejection(models.Model):
    rejection_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    rejected_quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])
    rejection_reason = models.TextField()
    rejection_proof_url = models.URLField(blank=True, null=True)
    digital_signature = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'order_item_rejections'

class SupplyOrder(models.Model):
    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    supply_order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    supplier_id = models.UUIDField()
    expected_delivery_date = models.DateTimeField()
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='pending')
    invoice_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    adjusted_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    quality_rating = models.DecimalField(max_digits=3, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(5)])
    on_time_rating = models.DecimalField(max_digits=3, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(5)])
    rejection_proof_url = models.URLField(blank=True, null=True)
    
    class Meta:
        db_table = 'supply_orders'

class DeliveryPartner(models.Model):
    PARTNER_TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('company', 'Company'),
    ]
    
    delivery_partner_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner_name = models.CharField(max_length=255)
    partner_type = models.CharField(max_length=20, choices=PARTNER_TYPE_CHOICES)
    contact_info = models.JSONField()
    is_active = models.BooleanField(default=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'delivery_partners'

class DeliveryTracking(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]
    
    tracking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    delivery_partner = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE)
    current_location = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    estimated_arrival = models.DateTimeField(blank=True, null=True)
    actual_arrival = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'delivery_tracking'

class BillingRecord(models.Model):
    BILLING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    billing_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    billing_status = models.CharField(max_length=20, choices=BILLING_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'billing_records'

class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
    ]
    
    CATEGORY_CHOICES = [
        ('order', 'Order'),
        ('booking', 'Booking'),
        ('loyalty', 'Loyalty'),
        ('other', 'Other'),
    ]
    
    transaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    source_entity_id = models.UUIDField()
    source_entity_type = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    payment_method_id = models.UUIDField(blank=True, null=True)
    gateway_transaction_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, default='pending')
    transaction_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'transactions'

class CustomerAccount(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('wallet', 'Wallet'),
        ('credit', 'Credit'),
        ('loyalty', 'Loyalty'),
    ]
    
    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    is_refundable = models.BooleanField(default=True)
    crypto_details = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'customer_accounts'

class PaymentMethod(models.Model):
    METHOD_TYPE_CHOICES = [
        ('card', 'Card'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('crypto', 'Cryptocurrency'),
    ]
    
    payment_method_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPE_CHOICES)
    provider = models.CharField(max_length=100)
    last_four_digits = models.CharField(max_length=4, blank=True, null=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_methods'

class StaffShift(models.Model):
    SHIFT_TYPE_CHOICES = [
        ('morning', 'Morning'),
        ('afternoon', 'Afternoon'),
        ('evening', 'Evening'),
        ('night', 'Night'),
    ]
    
    shift_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    shift_name = models.CharField(max_length=100)
    shift_type = models.CharField(max_length=20, choices=SHIFT_TYPE_CHOICES)
    shift_start = models.TimeField()
    shift_end = models.TimeField()
    max_staff_count = models.IntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'staff_shifts'

class StaffShiftAssignment(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('absent', 'Absent'),
    ]
    
    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_id = models.UUIDField()
    shift = models.ForeignKey(StaffShift, on_delete=models.CASCADE)
    assignment_date = models.DateField()
    actual_start_time = models.DateTimeField(blank=True, null=True)
    actual_end_time = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'staff_shift_assignments'

class TableAssignment(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]
    
    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_id = models.UUIDField()
    table = models.ForeignKey(RestaurantTable, on_delete=models.CASCADE)
    shift_assignment_id = models.UUIDField()
    assignment_start = models.DateTimeField()
    assignment_end = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'table_assignments'

class StaffPerformanceHistory(models.Model):
    METRIC_TYPE_CHOICES = [
        ('efficiency', 'Efficiency'),
        ('customer_rating', 'Customer Rating'),
        ('orders_served', 'Orders Served'),
        ('response_time', 'Response Time'),
    ]
    
    PERIOD_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    performance_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_id = models.UUIDField()
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPE_CHOICES)
    metric_value = models.DecimalField(max_digits=10, decimal_places=2)
    target_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    measured_at = models.DateTimeField()
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPE_CHOICES)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'staff_performance_history'

class CommunicationGroup(models.Model):
    GROUP_TYPE_CHOICES = [
        ('staff', 'Staff'),
        ('management', 'Management'),
        ('kitchen', 'Kitchen'),
        ('customer_service', 'Customer Service'),
    ]
    
    group_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'communication_groups'

class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('order_update', 'Order Update'),
        ('booking_confirmation', 'Booking Confirmation'),
        ('promotion', 'Promotion'),
        ('system', 'System'),
    ]
    
    notification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    source_entity_id = models.UUIDField()
    source_entity_type = models.CharField(max_length=50)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    action_url = models.URLField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'notifications'

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
    checked_in_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='checked_in_tickets')
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