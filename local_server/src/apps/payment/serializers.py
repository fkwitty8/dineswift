from rest_framework import serializers
from decimal import Decimal

class PaymentInitiateSerializer(serializers.Serializer):
    """Serializer for payment initiation"""
    order_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal(0.01))
    currency = serializers.CharField(default='UGX', max_length=3)
    payment_method = serializers.ChoiceField(
        choices=['momo', 'visa', 'mastercard', 'cash'],
        default='momo'
    )
    customer_phone = serializers.CharField(required=False)
    customer_email = serializers.EmailField(required=False)
    
    def validate(self, attrs):
        payment_method = attrs.get('payment_method')
        customer_phone = attrs.get('customer_phone')
        
        if payment_method == 'momo' and not customer_phone:
            raise serializers.ValidationError({
                'customer_phone': 'Phone number is required for Momo payments'
            })
        
        # Validate phone format for Momo
        if customer_phone and payment_method == 'momo':
            if not customer_phone.startswith('256'):
                raise serializers.ValidationError({
                    'customer_phone': 'Phone number must start with 256 for Uganda'
                })
        
        return attrs

class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status response"""
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    gateway_reference = serializers.CharField(required=False, allow_null=True)
    error_message = serializers.CharField(required=False, allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(required=False, allow_null=True)

class PaymentWebhookSerializer(serializers.Serializer):
    """Serializer for payment webhook data (Momo callback)"""
    transaction_id = serializers.CharField()
    status = serializers.ChoiceField(choices=['SUCCESSFUL', 'FAILED'])
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    payer_message = serializers.CharField(required=False, allow_blank=True)
    external_id = serializers.UUIDField()  # Our payment_id
    
    def validate_external_id(self, value):
        # Verify payment exists
        from apps.payment.models import Payment
        try:
            Payment.objects.get(id=value)
            return value
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Payment not found")