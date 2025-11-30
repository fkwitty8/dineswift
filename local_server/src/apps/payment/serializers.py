from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from .models import  CustomerWallet, Invoice, Payment, PaymentAllocation

class InvoiceCreateSerializer(serializers.Serializer):
    """Serializer for invoice creation"""
    order_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.01'),
        error_messages={
            'min_value': 'Amount must be greater than 0.00'
        }
    )
    tax_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.00'),
        default=Decimal('0.00')
    )
    service_fee = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.00'),
        default=Decimal('0.00')
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.00'),
        default=Decimal('0.00')
    )
    currency = serializers.CharField(default='UGX', max_length=3)
    due_date = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        # Validate that total amount is positive after calculations
        subtotal = attrs['amount']
        tax = attrs.get('tax_amount', Decimal('0.00'))
        service_fee = attrs.get('service_fee', Decimal('0.00'))
        discount = attrs.get('discount_amount', Decimal('0.00'))
        
        total_amount = subtotal + tax + service_fee - discount
        
        if total_amount <= Decimal('0.00'):
            raise serializers.ValidationError({
                'total_amount': 'Total amount must be greater than 0.00 after calculations'
            })
        
        # Set due_date if not provided (default to 24 hours from now)
        if not attrs.get('due_date'):
            attrs['due_date'] = timezone.now() + timezone.timedelta(hours=24)
        
        return attrs


class PaymentInitiateSerializer(serializers.Serializer):
    """Serializer for payment initiation with enhanced validation"""
    invoice_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(
        choices=[
            ('momo', 'Mobile Money'),
            ('visa', 'Visa Card'),
            ('mastercard', 'Mastercard'),
            ('cash', 'Cash'),
            ('wallet', 'Customer Wallet'),
            ('crypto', 'Cryptocurrency'),
            ('x_swift_stable_coin', 'X-Swift Stable Coin')
        ]
    )
    payment_method_id = serializers.UUIDField(
        required=False,
        help_text="Required for wallet payments, optional for cards"
    )
    customer_phone = serializers.CharField(
        required=False,
        max_length=20,
        help_text="Required for Momo payments, must start with 256"
    )
    customer_email = serializers.EmailField(
        required=False,
        help_text="Optional for receipt delivery"
    )
    
    def validate(self, attrs):
        payment_method = attrs.get('payment_method')
        customer_phone = attrs.get('customer_phone')
        payment_method_id = attrs.get('payment_method_id')
        invoice_id = attrs.get('invoice_id')

        # Validate invoice exists
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            attrs['invoice'] = invoice
        except Invoice.DoesNotExist:
            raise serializers.ValidationError({
                'invoice_id': 'Invoice not found'
            })

        # Momo validation
        if payment_method == 'momo':
            if not customer_phone:
                raise serializers.ValidationError({
                    'customer_phone': 'Phone number is required for Momo payments'
                })
            if customer_phone and not customer_phone.startswith('256'):
                raise serializers.ValidationError({
                    'customer_phone': 'Phone number must start with 256 for Uganda'
                })
            if customer_phone and len(customer_phone) != 12:
                raise serializers.ValidationError({
                    'customer_phone': 'Phone number must be 12 digits (including 256 prefix)'
                })

        # Wallet validation
        if payment_method == 'wallet':
            if not payment_method_id:
                raise serializers.ValidationError({
                    'payment_method_id': 'Payment method ID is required for wallet payments'
                })
        
        # Card validation
        if payment_method in ['visa', 'mastercard'] and payment_method_id:
            # Validate that payment method is a card
            try:
                payment_method_obj = PaymentMethod.objects.get(
                    id=payment_method_id,
                    method_type='CARD',
                    is_active=True
                )
                attrs['payment_method_obj'] = payment_method_obj
            except PaymentMethod.DoesNotExist:
                raise serializers.ValidationError({
                    'payment_method_id': 'Valid card payment method not found'
                })

        # Validate payment method exists and is active (for any stored method)
        if payment_method_id and payment_method != 'wallet':
            try:
                payment_method_obj = PaymentMethod.objects.get(
                    id=payment_method_id,
                    is_active=True
                )
                # Validate method type matches payment method
                method_type_map = {
                    'visa': 'CARD',
                    'mastercard': 'CARD',
                    'momo': 'MOBILE_MONEY',
                    'wallet': 'WALLET',
                    'crypto': 'CRYPTO',
                    'x_swift_stable_coin': 'CRYPTO'
                }
                
                expected_type = method_type_map.get(payment_method)
                if expected_type and payment_method_obj.method_type != expected_type:
                    raise serializers.ValidationError({
                        'payment_method_id': f'Payment method type mismatch. Expected {expected_type}'
                    })
                
                attrs['payment_method_obj'] = payment_method_obj
                
            except PaymentMethod.DoesNotExist:
                raise serializers.ValidationError({
                    'payment_method_id': 'Payment method not found or inactive'
                })

        return attrs


class PaymentAllocationSerializer(serializers.Serializer):
    """Serializer for payment allocation details"""
    allocation_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    allocated_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    allocation_date = serializers.DateTimeField()
    payment_status = serializers.CharField()
    payment_gateway = serializers.CharField()


class InvoiceStatusSerializer(serializers.Serializer):
    """Serializer for invoice status response"""
    invoice_id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    status = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2)
    is_fully_paid = serializers.BooleanField()
    is_overdue = serializers.BooleanField()
    due_date = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    allocations = PaymentAllocationSerializer(many=True, required=False)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status response"""
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    gateway = serializers.CharField()
    gateway_reference = serializers.CharField(
        required=False, 
        allow_null=True,
        allow_blank=True
    )
    error_message = serializers.CharField(
        required=False, 
        allow_null=True,
        allow_blank=True
    )
    allocated_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    unallocated_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    allocations = PaymentAllocationSerializer(many=True)
    customer_phone = serializers.CharField(required=False, allow_null=True)
    customer_email = serializers.EmailField(required=False, allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(required=False, allow_null=True)


class PaymentWebhookSerializer(serializers.Serializer):
    """Serializer for payment webhook data"""
    transaction_id = serializers.CharField(
        max_length=255,
        help_text="Gateway transaction reference"
    )
    status = serializers.ChoiceField(
        choices=['SUCCESSFUL', 'FAILED', 'PENDING'],
        help_text="Payment status from gateway"
    )
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Amount that was processed"
    )
    currency = serializers.CharField(
        max_length=3,
        default='UGX',
        help_text="Currency code"
    )
    payer_message = serializers.CharField(
        required=False, 
        allow_blank=True,
        max_length=500,
        help_text="Message from payer or gateway"
    )
    external_id = serializers.UUIDField(
        help_text="Our payment ID to update"
    )
    gateway_timestamp = serializers.DateTimeField(
        required=False,
        help_text="When the transaction occurred at the gateway"
    )
    metadata = serializers.JSONField(
        required=False,
        help_text="Additional gateway-specific data"
    )
    
    def validate_external_id(self, value):
        """Validate that payment exists and can be updated"""
        from .models import Payment
        
        try:
            payment = Payment.objects.get(id=value)
            
            # Check if payment can be updated (not already completed/refunded)
            if payment.status in ['COMPLETED', 'REFUNDED']:
                raise serializers.ValidationError(
                    f"Cannot update payment with status: {payment.status}"
                )
                
            return value
            
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Payment not found")


class WalletBalanceSerializer(serializers.Serializer):
    """Serializer for wallet balance"""
    wallet_id = serializers.UUIDField()
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    wallet_type = serializers.CharField()
    status = serializers.CharField()
    is_refundable = serializers.BooleanField()
    last_transaction_at = serializers.DateTimeField(required=False, allow_null=True)


class AddFundsSerializer(serializers.Serializer):
    """Serializer for adding funds to wallet"""
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.01'),
        error_messages={
            'min_value': 'Amount must be greater than 0.00'
        }
    )
    currency = serializers.CharField(default='UGX', max_length=3)
    reference_type = serializers.ChoiceField(
        choices=[
            ('payment', 'Payment'),
            ('manual_adjustment', 'Manual Adjustment'),
            ('promotion', 'Promotion'),
            ('refund', 'Refund'),
            ('transfer', 'Transfer')
        ]
    )
    reference_id = serializers.UUIDField(required=False)
    description = serializers.CharField(
        max_length=500,
        help_text="Description of the funds addition"
    )
    
    def validate(self, attrs):
        amount = attrs['amount']
        reference_type = attrs['reference_type']
        reference_id = attrs.get('reference_id')
        
        # For certain reference types, reference_id might be required
        if reference_type in ['payment', 'refund'] and not reference_id:
            raise serializers.ValidationError({
                'reference_id': f'Reference ID is required for {reference_type} type'
            })
        
        # Validate maximum deposit amount (optional business rule)
        max_deposit = Decimal('1000000.00')  # 1 million UGX
        if amount > max_deposit:
            raise serializers.ValidationError({
                'amount': f'Deposit amount cannot exceed {max_deposit}'
            })
        
        return attrs


class WalletTransactionSerializer(serializers.Serializer):
    """Serializer for wallet transaction history"""
    transaction_id = serializers.UUIDField()
    transaction_type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    running_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference_type = serializers.CharField(allow_null=True)
    reference_id = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    description = serializers.CharField()
    created_at = serializers.DateTimeField()
    processed_at = serializers.DateTimeField()


class OrderPaymentsSerializer(serializers.Serializer):
    """Serializer for order payments summary"""
    order_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    invoice_status = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2)
    is_fully_paid = serializers.BooleanField()
    is_overdue = serializers.BooleanField()
    due_date = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    payments = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of payment allocations with details"
    )

class PaymentAllocationCreateSerializer(serializers.Serializer):
    """Serializer for manual payment allocation"""
    payment_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.01')
    )
    
    def validate(self, attrs):
        payment_id = attrs['payment_id']
        invoice_id = attrs['invoice_id']
        amount = attrs['amount']
        
        # Validate payment exists and has sufficient unallocated amount
        try:
            payment = Payment.objects.get(id=payment_id)
            if payment.unallocated_amount < amount:
                raise serializers.ValidationError({
                    'amount': f'Payment only has {payment.unallocated_amount} unallocated, requested {amount}'
                })
        except Payment.DoesNotExist:
            raise serializers.ValidationError({
                'payment_id': 'Payment not found'
            })
        
        # Validate invoice exists and has sufficient amount due
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            if invoice.amount_due < amount:
                raise serializers.ValidationError({
                    'amount': f'Invoice only has {invoice.amount_due} due, requested {amount}'
                })
        except Invoice.DoesNotExist:
            raise serializers.ValidationError({
                'invoice_id': 'Invoice not found'
            })
        
        # Check if allocation already exists
        if PaymentAllocation.objects.filter(payment_id=payment_id, invoice_id=invoice_id).exists():
            raise serializers.ValidationError({
                'payment_id': 'Payment already allocated to this invoice'
            })
        
        attrs['payment'] = payment
        attrs['invoice'] = invoice
        return attrs

#serializer for cash completion
class CashPaymentCompleteSerializer(serializers.Serializer):
    """Serializer for staff to confirm cash collection"""
    payment_id = serializers.UUIDField()
    staff_user_id = serializers.UUIDField()
    collected_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        min_value=Decimal('0.01')
    )
    
    def validate(self, attrs):
        payment_id = attrs['payment_id']
        collected_amount = attrs['collected_amount']
        
        try:
            payment = Payment.objects.get(
                id=payment_id, 
                status='AWAITING_COLLECTION'
            )
            
            if collected_amount != payment.amount:
                raise serializers.ValidationError({
                    'collected_amount': f'Collected amount {collected_amount} does not match expected amount {payment.amount}'
                })
                
            attrs['payment'] = payment
            return attrs
            
        except Payment.DoesNotExist:
            raise serializers.ValidationError({
                'payment_id': 'Payment not found or not awaiting collection'
            })

class RefundRequestSerializer(serializers.Serializer):
    """Serializer for refund requests"""
    payment_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        min_value=Decimal('0.01')
    )
    reason = serializers.CharField(
        max_length=500,
        help_text="Reason for the refund"
    )
    refund_to_original_method = serializers.BooleanField(
        default=True,
        help_text="Whether to refund to original payment method"
    )
    alternative_method_id = serializers.UUIDField(
        required=False,
        help_text="Alternative payment method for refund (if not original)"
    )
    
    def validate(self, attrs):
        payment_id = attrs['payment_id']
        amount = attrs['amount']
        refund_to_original = attrs.get('refund_to_original_method', True)
        alternative_method_id = attrs.get('alternative_method_id')
        
        # Validate payment exists and is refundable
        try:
            payment = Payment.objects.get(id=payment_id)
            
            if payment.status != 'COMPLETED':
                raise serializers.ValidationError({
                    'payment_id': 'Only completed payments can be refunded'
                })
            
            if payment.allocated_amount < amount:
                raise serializers.ValidationError({
                    'amount': f'Refund amount exceeds allocated amount: {payment.allocated_amount}'
                })
                
        except Payment.DoesNotExist:
            raise serializers.ValidationError({
                'payment_id': 'Payment not found'
            })
        
        # Validate alternative method if provided
        if not refund_to_original and not alternative_method_id:
            raise serializers.ValidationError({
                'alternative_method_id': 'Alternative payment method required when not refunding to original method'
            })
        
        if alternative_method_id:
            try:
                PaymentMethod.objects.get(id=alternative_method_id, is_active=True)
            except PaymentMethod.DoesNotExist:
                raise serializers.ValidationError({
                    'alternative_method_id': 'Alternative payment method not found or inactive'
                })
        
        attrs['payment'] = payment
        return attrs