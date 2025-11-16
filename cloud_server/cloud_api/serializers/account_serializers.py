from rest_framework import serializers
from ..models import CustomerAccount, Transaction
from decimal import Decimal

class CustomerAccountSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    class Meta:
        model = CustomerAccount
        fields = ['account_id', 'user', 'restaurant', 'balance', 'account_type', 
                 'is_refundable', 'restaurant_name', 'created_at', 'updated_at']
        read_only_fields = ['account_id', 'balance', 'created_at', 'updated_at']

class DepositSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1.00'))
    phone = serializers.CharField(max_length=15)
    provider = serializers.ChoiceField(choices=['mtn', 'airtel'])
    reference = serializers.CharField(max_length=100)
    
class WithdrawSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1.00'))
    reason = serializers.CharField(max_length=255, required=False)
    
    def validate_amount(self, value):
        account = self.context['account']
        if value > account.balance:
            raise serializers.ValidationError("Insufficient balance")
        return value