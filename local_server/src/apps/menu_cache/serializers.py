from rest_framework import serializers
from .models import MenuCache

class MenuItemSerializer(serializers.Serializer):
    """Serializer for individual menu items (nested in menu data)"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    category = serializers.CharField()
    is_available = serializers.BooleanField(default=True)
    preparation_time = serializers.IntegerField(min_value=0)
    ingredients = serializers.ListField(child=serializers.CharField(), required=False)
    allergens = serializers.ListField(child=serializers.CharField(), required=False)
    image_url = serializers.URLField(required=False, allow_null=True)

class MenuCategorySerializer(serializers.Serializer):
    """Serializer for menu categories"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    items = MenuItemSerializer(many=True)

class MenuCacheSerializer(serializers.ModelSerializer):
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
        return MenuCategorySerializer(categories, many=True).data

class MenuSyncSerializer(serializers.Serializer):
    """Serializer for menu sync requests"""
    force_refresh = serializers.BooleanField(default=False)
    restaurant_id = serializers.UUIDField(required=False)
    
    def validate(self, attrs):
        # If no restaurant_id provided, use the authenticated user's restaurant
        if 'restaurant_id' not in attrs and self.context.get('request'):
            attrs['restaurant_id'] = self.context['request'].user.restaurant_id
        return attrs