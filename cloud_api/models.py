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
        ]

class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role_name = models.CharField(max_length=50, unique=True)
    permissions = models.JSONField()
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
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

