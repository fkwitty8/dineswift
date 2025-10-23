from rest_framework import serializers
from .models import Order, SalesOrder, OrderItem, MenuItem, RestaurantTable, Booking, Payment, Supplier, RestaurantSupplier, SupplyOrder


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['source_entity_id', 'source_entity_type', 'quantity', 
                  'unit_price', 'total_price', 'special_instructions']


class SalesOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrder
        fields = ['customer_user', 'order_subtype', 'table', 'assigned_waiter']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    sales_order = SalesOrderSerializer(write_only=True)
    
    class Meta:
        model = Order
        fields = ['restaurant', 'order_type', 'status', 'total_amount', 
                  'notes', 'items', 'sales_order']
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        sales_order_data = validated_data.pop('sales_order')
        
        order = Order.objects.create(**validated_data)
        
        SalesOrder.objects.create(order=order, **sales_order_data)
        
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        return order


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['id', 'item_name', 'description', 'sales_price', 
                  'preparation_time', 'is_available']


class BookingSerializer(serializers.ModelSerializer):
    deposit_policy = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = ['customer_user', 'restaurant', 'table', 'booking_date', 
                  'start_time', 'end_time', 'party_size', 'deposit_amount', 
                  'deposit_status', 'special_requests', 'deposit_policy']
    
    def get_deposit_policy(self, obj):
        return {
            'policy': 'Deposit is fully refundable up to 24 hours before booking time. '
                     'Cancellations within 24 hours will forfeit the deposit.',
            'refund_deadline_hours': 24
        }


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['idempotency_key', 'payment_type', 'reference_id', 
                  'amount', 'phone_number']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'company_name', 'contact_person', 'contact_info', 
                  'address', 'business_registration', 'payment_terms', 
                  'rating', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class RestaurantSupplierSerializer(serializers.ModelSerializer):
    supplier_details = SupplierSerializer(source='supplier', read_only=True)
    
    class Meta:
        model = RestaurantSupplier
        fields = ['id', 'restaurant', 'supplier', 'relationship_status', 
                  'is_preferred', 'payment_terms', 'delivery_lead_time', 
                  'supplier_details', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class SupplyOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    
    class Meta:
        model = SupplyOrder
        fields = ['id', 'supplier', 'expected_delivery_date', 'delivery_status', 
                  'invoice_total', 'items']
        read_only_fields = ['id']
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        supplier = validated_data.pop('supplier')
        restaurant = self.context['restaurant']
        
        order = Order.objects.create(
            restaurant=restaurant,
            order_type='supply',
            status='pending',
            total_amount=validated_data['invoice_total']
        )
        
        supply_order = SupplyOrder.objects.create(
            order=order,
            supplier=supplier,
            **validated_data
        )
        
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        return supply_order
