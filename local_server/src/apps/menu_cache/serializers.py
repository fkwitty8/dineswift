from rest_framework import serializers
from .models import MenuCache
from django.core.validators import MinValueValidator

class BaseMenuItemSerializer(serializers.Serializer):
    """Serializer for individual menu items (nested in menu data)"""
    id = serializers.UUIDField(error_messages={'invalid': 'Must be a valid UUID.'})
    name = serializers.CharField(error_messages={'blank': 'Name cannot be blank.'})
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    category = serializers.CharField(error_messages={'blank': 'Category cannot be blank.'})
    is_available = serializers.BooleanField(default=True)
    preparation_time = serializers.IntegerField(min_value=0, required=False, default=0)
    ingredients = serializers.ListField(child=serializers.CharField(), required=False)
    allergens = serializers.ListField(child=serializers.CharField(), required=False)
    image_url = serializers.URLField(required=False, allow_null=True)

class BaseMenuCategorySerializer(serializers.Serializer):
    """Serializer for menu categories"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    items = BaseMenuItemSerializer(many=True)

class BaseMenuCacheSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    menu_items_count = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuCache
        fields = [
            'id', 'restaurant', 'restaurant_name', 'version', 'checksum',
            'is_active', 'last_synced', 'menu_items_count', 'categories',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_menu_items_count(self, obj):
        """Count total menu items"""
        menu_data = obj.menu_data or {}
        categories = menu_data.get('categories', [])
        return sum(len(category.get('items', [])) for category in categories)
    
    def get_categories(self, obj):
        """Extract and serialize categories from menu_data"""
        menu_data = obj.menu_data or {}
        categories = menu_data.get('categories', [])
        return BaseMenuCategorySerializer(categories, many=True).data

class BaseMenuSyncSerializer(serializers.Serializer):
    """Serializer for menu sync requests"""
    force_refresh = serializers.BooleanField(default=False)
    restaurant_id = serializers.UUIDField(required=False)
    
    def validate(self, attrs):
        # If no restaurant_id provided, use the authenticated user's restaurant
        request = self.context.get('request')
        if 'restaurant_id' not in attrs and request and hasattr(request.user, 'restaurant_id'):
            attrs['restaurant_id'] = request.user.restaurant_id
        return attrs
    
    
    
# apps/menu_cache/

# ├── api/

# │   ├── init.py

# │   ├── v1/

# │   │   ├── init.py

# │   │   ├── serializers.py    # Inherits from global serializers

# │   │   ├── urls.py           # v1 endpoints

# │   │   └── views.py          # Legacy Logic

# │   └── v2/

# │       ├── init.py

# │       ├── serializers.py    # Inherits/Extends V1 or Global

# │       ├── urls.py           # v2 endpoints

# │       └── views.py          # Modern Logic

# ├── services/                 # THE BRAIN (Shared Business Logic)

# │   ├── init.py           # Exports Services

# │   ├── base.py               # Shared DB queries & ABC

# │   ├── legacy_service.py     # V1 specific business rules

# │   └── modern_service.py     # V2 specific business rules (Redis, etc.)

# ├── models.py                 # Single source of truth for Data

# ├── serializers.py            # GLOBAL: Shared BaseSerializers for DRY code

# ├── urls.py                   # APPS ROUTER (v1/, v2/, v3/)

# ├── exceptions.py             # App-specific error classes

# └── utils.py                  # Tiny helper functions (hashing, math)