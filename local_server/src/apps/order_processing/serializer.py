from rest_framework import serializers
from decimal import Decimal
from .models import OfflineOrder, OrderCRDTState

class OrderItemSerializer(serializers.Serializer):
    """Serializer for individual order items"""
    id = serializers.UUIDField()
    name = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    special_instructions = serializers.CharField(required=False, allow_blank=True)
    modifiers = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list
    )
    
    def validate(self, attrs):
        # Calculate total price
        quantity = attrs['quantity']
        price = attrs['price']
        attrs['total_price'] = Decimal(quantity) * price
        return attrs

# In your serializer.py, update the OrderCreateSerializer:
class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemSerializer(many=True, min_length=1)
    table_id = serializers.UUIDField(required=False, allow_null=True)
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    special_instructions = serializers.CharField(required=False, allow_blank=True)
    estimated_preparation_time = serializers.IntegerField(min_value=1, required=False)
    payment_method = serializers.ChoiceField(
        choices=['momo', 'cash', 'card', 'account'],
        default='cash'
    )
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        # Only validate phone for momo payments
        if attrs.get('payment_method') == 'momo' and not attrs.get('customer_phone'):
            raise serializers.ValidationError({
                'customer_phone': 'Phone number is required for Momo payments'
            })
        return attrs

class OrderSerializer(serializers.ModelSerializer):
    """Serializer for order details"""
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    items_detail = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_order_status_display', read_only=True)
    sync_status_display = serializers.CharField(source='get_sync_status_display', read_only=True)
    
    class Meta:
        model = OfflineOrder
        fields = [
            'id', 'local_order_id', 'restaurant', 'restaurant_name', 'table_id',
            'customer_id', 'order_items', 'items_detail', 'total_amount', 'tax_amount',
            'special_instructions', 'order_status', 'status_display', 'sync_status',
            'sync_status_display', 'estimated_preparation_time', 'actual_preparation_time',
            'preparation_started_at', 'completed_at', 'supabase_order_id',
            'sync_attempts', 'sync_error', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'local_order_id', 'total_amount', 'tax_amount', 'created_at', 'updated_at'
        ]
    
    def get_items_detail(self, obj):
        """Serialize order items with additional details"""
        return OrderItemSerializer(obj.order_items, many=True).data

class OrderStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating order status"""
    status = serializers.ChoiceField(choices=OfflineOrder.STATUS_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_status(self, value):
        # Add business logic for status transitions
        current_status = self.instance.order_status if self.instance else None
        
        valid_transitions = {
            'PENDING': ['CONFIRMED', 'CANCELLED'],
            'CONFIRMED': ['PREPARING', 'CANCELLED'],
            'PREPARING': ['READY', 'CANCELLED'],
            'READY': ['COMPLETED'],
            'COMPLETED': [],  # Final state
            'CANCELLED': [],  # Final state
        }
        
        if current_status and value not in valid_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f"Cannot transition from {current_status} to {value}"
            )
        
        return value

class OrderWithPaymentSerializer(serializers.Serializer):
    """Combined order and payment data"""
    order = OrderSerializer()
    payment = serializers.DictField(required=False)
    
    def to_representation(self, instance):
        """Custom representation for combined data"""
        order_data = OrderSerializer(instance['order']).data
        payment_data = instance.get('payment', {})
        
        return {
            'order': order_data,
            'payment': payment_data
        }