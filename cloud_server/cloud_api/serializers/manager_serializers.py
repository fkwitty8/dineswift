from rest_framework import serializers
from ..models import Menu, MenuItem, Restaurant

class MenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Menu
        fields = ['id', 'restaurant', 'name', 'description', 'is_active', 'version', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['id', 'menu', 'item_name', 'description', 'sales_price', 'preparation_time', 
                 'department', 'is_available', 'display_order', 'image', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class MenuWithItemsSerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(source='menuitem_set', many=True, read_only=True)
    
    class Meta:
        model = Menu
        fields = ['id', 'restaurant', 'name', 'description', 'is_active', 'version', 
                 'created_at', 'updated_at', 'items']
        read_only_fields = ['id', 'created_at', 'updated_at']