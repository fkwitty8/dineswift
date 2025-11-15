from rest_framework import serializers
from .models import Order, OrderItem, SalesOrder, BillingRecord, Menu, MenuItem

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'source_entity_id', 'source_entity_type', 'quantity', 'unit_price', 'total_price', 'special_instructions']

class BillingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingRecord
        fields = ['billing_id', 'subtotal_amount', 'tax_amount', 'service_charge', 'discount_amount', 'total_amount', 'billing_status']

class SalesOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrder
        fields = ['id', 'customer_user', 'order_subtype', 'table', 'assigned_waiter', 'otp_code']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, source='orderitem_set')
    sales_order = SalesOrderSerializer(read_only=True)
    billing = BillingRecordSerializer(read_only=True)
    
    class Meta:
        model = Order
        fields = ['id', 'restaurant', 'order_type', 'status', 'total_amount', 'notes', 'created_at', 'updated_at', 'items', 'sales_order', 'billing']
    
    def create(self, validated_data):
        items_data = validated_data.pop('orderitem_set')
        order = Order.objects.create(**validated_data)
        
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        # Auto-generate digital ticket for confirmed orders
        if order.status == 'confirmed':
            from .ticket_utils import generate_digital_ticket
            generate_digital_ticket(order)
        
        return order

class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['id', 'item_name', 'description', 'sales_price', 'preparation_time', 'department', 'is_available']

class MenuItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['menu', 'item_name', 'description', 'sales_price', 'preparation_time', 'department', 'is_available', 'display_order', 'image']
        
    def validate_sales_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Sales price must be greater than 0")
        return value
        
    def validate_preparation_time(self, value):
        if value <= 0:
            raise serializers.ValidationError("Preparation time must be greater than 0")
        return value

class MenuSerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, source='menuitem_set', read_only=True)
    
    class Meta:
        model = Menu
        fields = ['id', 'name', 'description', 'is_active', 'version', 'items']