from rest_framework import serializers
from .models import OTP
from django.db import DatabaseError
import logging 
logger = logging.getLogger('dineswift')

class OTPGenerateSerializer(serializers.Serializer):
    """Serializer for OTP generation requests"""
    order_id = serializers.UUIDField()
    expiry_minutes = serializers.IntegerField(min_value=1, max_value=60, default=15)
    
    def validate_order_id(self, value):
        # Verify order exists and belongs to restaurant
        from apps.order_processing.models import OfflineOrder
        
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            try:
                order = OfflineOrder.objects.get(
                    id=value,
                    restaurant_id=str(request.user.restaurant_id)
                )
                return value
            except OfflineOrder.DoesNotExist:
                raise serializers.ValidationError("Order not found")
            except DatabaseError:
                # Log the error for production, but raise a generic error for the user/test
                logger.error("Database error during order validation lookup.") 
                raise serializers.ValidationError("A temporary service error occurred. Please try again.")
        return value

class OTPVerifySerializer(serializers.Serializer):
    """Serializer for OTP verification"""
    order_id = serializers.UUIDField()
    otp_code = serializers.CharField(min_length=6, max_length=6)
    
    def validate_otp_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits")
        return value

class OTPSerializer(serializers.ModelSerializer):
    """Serializer for OTP model"""
    order_local_id = serializers.CharField(source='order.local_order_id', read_only=True)
    is_expired = serializers.SerializerMethodField()
    class Meta:
        model = OTP
        fields = [
            'id', 'order_id', 'order_local_id', 'otp_code', 'status',
            'expires_at', 'verified_at', 
            'is_expired',  'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_is_expired(self, obj):
        return not obj.is_valid()
    