from rest_framework import serializers
from .models import *

class RestaurantSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    halal_status_display = serializers.CharField(source='get_halal_status_display', read_only=True)
    
    class Meta:
        model = Restaurant
        fields = [
            'restaurant_id', 'name', 'description', 'cuisine_type', 
            'logo', 'logo_url', 'halal_status', 'halal_status_display',
            'halal_certification_number', 'halal_certification_authority',
            'address', 'contact_info', 'operation_hours', 'social_media_links',
            'delivery_options', 'payment_methods_accepted', 'average_rating',
            'total_reviews', 'average_delivery_time', 'status', 'created_at'
        ]
    
    def get_logo_url(self, obj):
        if obj.logo:
            return obj.logo.url
        return obj.logo_url

class MenuItemSerializer(serializers.ModelSerializer):
    dietary_categories_display = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuItem
        fields = [
            'menu_item_id', 'item_name', 'description', 'sales_price',
            'preparation_time', 'department', 'dietary_categories',
            'dietary_categories_display', 'is_halal', 'halal_certified',
            'is_available', 'display_order', 'created_at'
        ]
    
    def get_dietary_categories_display(self, obj):
        return [MenuItem.DietaryCategory(category).label for category in obj.dietary_categories]

class MenuSerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)
    restaurant_details = RestaurantSerializer(source='restaurant', read_only=True)
    
    class Meta:
        model = Menu
        fields = ['menu_id', 'restaurant', 'restaurant_details', 'name', 'description', 'is_active', 'version', 'items']

class RestaurantTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantTable
        fields = '__all__'

class BookingSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer_user.full_name', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    table_number = serializers.CharField(source='table.table_number', read_only=True)
    
    class Meta:
        model = Booking
        fields = '__all__'

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'

class SalesOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrder
        fields = '__all__'