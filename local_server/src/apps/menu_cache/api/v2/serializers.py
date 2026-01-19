"""
V2 Serializers - Flutter App with Enhanced Features
Inherits from global base serializers
"""
from rest_framework import serializers
from apps.menu_cache.serializers import (
    BaseMenuItemSerializer,
    BaseMenuCategorySerializer,
    BaseMenuCacheSerializer,
    BaseMenuSyncSerializer,
    get_categories_data
)


class MenuItemV2Serializer(BaseMenuItemSerializer):
    """V2-specific menu item with Flutter enhancements"""
    # Flutter-specific fields
    dietary_tags = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=[],
        help_text="Dietary restrictions/tags"
    )
    spice_level = serializers.IntegerField(
        min_value=0, 
        max_value=5, 
        default=0,
        help_text="Spice level 0-5"
    )
    customizations = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=[],
        help_text="Available customizations"
    )
    image_url = serializers.URLField(
        required=False, 
        allow_null=True,
        help_text="High-res image for Flutter"
    )
    thumbnail_url = serializers.URLField(
        required=False, 
        allow_null=True,
        help_text="Optimized thumbnail"
    )
    
    # Override base field with V2 enhancements
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        style={'base_template': 'textarea.html'},  # Rich text support
        help_text="Rich description with formatting"
    )
    
    # Computed fields for Flutter
    display_price = serializers.SerializerMethodField()
    
    def get_display_price(self, obj):
        """Format price for Flutter display"""
        price = obj.get('price', 0)
        return f"${float(price):.2f}" if price else "$0.00"


class MenuCategoryV2Serializer(BaseMenuCategorySerializer):
    """V2-specific category with Flutter UI enhancements"""
    # Flutter UI fields
    display_order = serializers.IntegerField(default=0)
    icon = serializers.CharField(
        required=False, 
        allow_blank=True,
        help_text="Material icon name"
    )
    color = serializers.CharField(
        required=False,
        default='#4CAF50',
        help_text="Category color in hex"
    )
    is_featured = serializers.BooleanField(
        default=False,
        help_text="Featured category in Flutter"
    )
    
    # Use V2 item serializer
    items = MenuItemV2Serializer(many=True)


class MenuCacheV2Serializer(BaseMenuCacheSerializer):
    """V2 serializer for MenuCache with Flutter optimizations"""
    # V2-specific fields
    categories = serializers.SerializerMethodField()
    menu_summary = serializers.SerializerMethodField()
    restaurant_logo = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()
    
    class Meta(BaseMenuCacheSerializer.Meta):
        # Extend base fields
        fields = BaseMenuCacheSerializer.Meta.fields + [
            'categories', 
            'menu_summary',
            'restaurant_logo',
            'features'
        ]
    
    def get_categories(self, obj):
        """Use V2 category serializer"""
        return get_categories_data(obj, MenuCategoryV2Serializer)
    
    def get_menu_summary(self, obj):
        """Enhanced summary for Flutter"""
        menu_data = obj.menu_data or {}
        categories = menu_data.get('categories', [])
        total_items = self.get_menu_items_count(obj)
        
        # Calculate price range
        all_prices = []
        for category in categories:
            for item in category.get('items', []):
                price = item.get('price')
                if price:
                    all_prices.append(float(price))
        
        return {
            'total_items': total_items,
            'total_categories': len(categories),
            'price_range': {
                'min': min(all_prices) if all_prices else 0,
                'max': max(all_prices) if all_prices else 0,
                'currency': 'USD'
            }
        }
    
    def get_restaurant_logo(self, obj):
        """Get logo for Flutter display"""
        if obj.restaurant and hasattr(obj.restaurant, 'logo_url'):
            return obj.restaurant.logo_url
        return None
    
    def get_features(self, obj):
        """Flutter feature flags"""
        return {
            'supports_images': True,
            'supports_customizations': True,
            'supports_dietary_filters': True,
            'supports_real_time': True,
            'api_version': '2.0'
        }


class MenuSyncV2Serializer(BaseMenuSyncSerializer):
    """V2-specific sync with advanced options"""
    # Advanced sync options for Flutter
    include_metadata = serializers.BooleanField(default=True)
    include_images = serializers.BooleanField(default=True)
    include_customizations = serializers.BooleanField(default=True)
    compression = serializers.ChoiceField(
        choices=['none', 'gzip', 'brotli'],
        default='gzip',
        help_text="Response compression for mobile data savings"
    )
    
    # Pagination for large menus
    page = serializers.IntegerField(
        min_value=1, 
        default=1,
        required=False
    )
    page_size = serializers.IntegerField(
        min_value=1, 
        max_value=100,
        default=50,
        required=False
    )
    
    # Override validation for V2
    def validate(self, attrs):
        attrs = super().validate(attrs)
        
        # V2-specific business rules
        if attrs.get('include_images') and not attrs.get('compression'):
            # Recommend compression for images
            attrs['compression'] = 'gzip'
        
        return attrs