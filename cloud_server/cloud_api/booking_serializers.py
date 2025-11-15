from rest_framework import serializers
from .models import Booking, RestaurantTable, MenuItem
from decimal import Decimal

class BookingSerializer(serializers.ModelSerializer):
    table_number = serializers.CharField(source='table.table_number', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    class Meta:
        model = Booking
        fields = ['id', 'customer_user', 'restaurant', 'table', 'booking_date', 'start_time', 
                 'end_time', 'party_size', 'status', 'deposit_amount', 'deposit_status', 
                 'special_requests', 'table_number', 'restaurant_name', 'created_at']
        read_only_fields = ['id', 'created_at', 'deposit_status']
    
    def validate(self, data):
        # Check table availability
        existing_booking = Booking.objects.filter(
            table=data['table'],
            booking_date=data['booking_date'],
            start_time__lt=data['end_time'],
            end_time__gt=data['start_time'],
            status__in=['confirmed', 'checked_in']
        ).exists()
        
        if existing_booking:
            raise serializers.ValidationError("Table not available for selected time")
        
        # Calculate required deposit (10% of estimated bill or minimum $5)
        estimated_bill = data['party_size'] * Decimal('25.00')  # Average per person
        data['deposit_amount'] = max(estimated_bill * Decimal('0.10'), Decimal('5.00'))
        
        return data

class BookingMenuItemSerializer(serializers.Serializer):
    menu_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    
class PreOrderBookingSerializer(BookingSerializer):
    menu_items = BookingMenuItemSerializer(many=True, required=False)
    
    def create(self, validated_data):
        menu_items_data = validated_data.pop('menu_items', [])
        booking = super().create(validated_data)
        
        # Store pre-ordered items in special_requests as JSON
        if menu_items_data:
            booking.special_requests = f"Pre-order: {menu_items_data}"
            booking.save()
        
        return booking