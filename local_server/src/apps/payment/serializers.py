# serializers.py
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from decimal import Decimal
import uuid
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db import transaction

from .models import (
    Invoice, Payment, PaymentAllocation, 
    AccountingEntry, CustomerWallet, WalletTransaction
)
from apps.core.models import Restaurant
from apps.order_processing.models import OfflineOrder


# ====================== BASE SERIALIZERS ======================

class TimestampSerializerMixin(serializers.Serializer):
    """Mixin for timestamp fields"""
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class UUIDSerializerMixin(serializers.Serializer):
    """Mixin for UUID fields"""
    id = serializers.UUIDField(read_only=True, default=uuid.uuid4)


# ====================== INVOICE SERIALIZERS ======================

class InvoiceAmountBreakdownSerializer(serializers.Serializer):
    """Serializer for invoice amount breakdown validation"""
    subtotal_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    tax_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    service_fee = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )

class InvoiceCreateSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for creating invoices"""
    order_id = serializers.UUIDField(required=True)
    restaurant_id = serializers.UUIDField(required=True)
    subtotal_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True
    )
    tax_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True
    )
    service_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True
    )
    discount_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True
    )
    total_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    class Meta:
        model = Invoice
        fields = [
            'id', 'order_id', 'restaurant_id', 'subtotal_amount', 
            'tax_amount', 'service_fee', 'discount_amount',
            'created_at', 'updated_at'
        ]
    
    def validate(self, attrs):
        # Validate order exists and belongs to restaurant
        try:
            order = OfflineOrder.objects.get(
                id=attrs['order_id'],
                restaurant_id=attrs['restaurant_id']
            )
            attrs['order'] = order
        except OfflineOrder.DoesNotExist:
            raise serializers.ValidationError(
                {'order_id': 'Order not found for the given restaurant.'}
            )
            
        # Validate Invoice Subtotal matches Order Total
        invoice_subtotal = attrs['subtotal_amount']
        order_total_amount = order.total_amount 
        
        # We must account for tax and fees being added after the order's base total
        if invoice_subtotal != order_total_amount:
            raise serializers.ValidationError(
                {'subtotal_amount': f"Invoice subtotal ({invoice_subtotal}) does not match the order's item total ({order_total_amount})."}
            )
        
        # Calculate total amount
        total = (
            attrs['subtotal_amount'] + 
            attrs['tax_amount'] + 
            attrs['service_fee'] - 
            attrs['discount_amount']
        )
        
        if total <= 0:
            raise serializers.ValidationError(
                {'total_amount': 'Total amount must be greater than zero.'}
            )
        
        attrs['total_amount'] = total
        attrs['restaurant_id'] = attrs['restaurant_id']
        
        return attrs
    
    def create(self, validated_data):
        # Extract order from validated data
        order = validated_data.pop('order')
        
        # Create invoice
        invoice = Invoice.objects.create(
            order=order,
            restaurant_id=validated_data['restaurant_id'],
            subtotal_amount=validated_data['subtotal_amount'],
            tax_amount=validated_data['tax_amount'],
            service_fee=validated_data['service_fee'],
            discount_amount=validated_data['discount_amount'],
            total_amount=validated_data['total_amount'],
            due_date=timezone.now() + timezone.timedelta(hours=24),
            status='ISSUED'
        )
        
        return invoice


class InvoiceReadSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for reading invoice details"""
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    restaurant_id = serializers.UUIDField(read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    # Amount fields
    subtotal_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    service_fee = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Computed fields
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    
    # Status and dates
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    issue_date = serializers.DateTimeField(read_only=True)
    due_date = serializers.DateTimeField(read_only=True)
    paid_at = serializers.DateTimeField(read_only=True, allow_null=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'order_id', 'restaurant_id', 'restaurant_name',
            'subtotal_amount', 'tax_amount', 'service_fee', 'discount_amount',
            'total_amount', 'amount_paid', 'amount_due', 'is_fully_paid',
            'is_overdue', 'status', 'status_display', 'issue_date', 'due_date',
            'paid_at', 'created_at', 'updated_at'
        ]


class InvoiceStatusSerializer(serializers.ModelSerializer):
    """Serializer for invoice status and allocations"""
    allocations = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'status', 'total_amount', 'amount_paid', 'amount_due',
            'is_fully_paid', 'is_overdue', 'due_date', 'paid_at',
            'allocations', 'created_at', 'updated_at'
        ]
    
    def get_allocations(self, obj):
        from .serializers import PaymentAllocationReadSerializer
        allocations = obj.allocations.select_related('payment').all()
        return PaymentAllocationReadSerializer(allocations, many=True).data


# ====================== PAYMENT SERIALIZERS ======================

class PaymentInitiateSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for initiating payments"""
    invoice_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        required=False
    )
    payment_method = serializers.ChoiceField(
        choices=[choice[0] for choice in Payment.GATEWAY_CHOICES],
        required=True
    )
    customer_phone = serializers.CharField(
        max_length=20, 
        required=False, 
        allow_null=True
    )
    customer_email = serializers.EmailField(
        required=False, 
        allow_null=True
    )
    metadata = serializers.JSONField(required=False, default=dict)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice_id', 'amount', 'payment_method',
            'customer_phone', 'customer_email', 'metadata',
            'created_at', 'updated_at'
        ]
    
    def validate(self, attrs):
        # Validate invoice exists and is payable
        try:
            invoice = Invoice.objects.get(
                id=attrs['invoice_id'],
                status__in=['DRAFT', 'ISSUED', 'PARTIALLY_PAID']
            )
            attrs['invoice'] = invoice
            
            # If amount not provided, use invoice total
            if 'amount' not in attrs:
                attrs['amount'] = invoice.total_amount
            
            # Validate amount doesn't exceed invoice amount due
            if attrs['amount'] > invoice.amount_due:
                raise serializers.ValidationError(
                    {'amount': f'Payment amount cannot exceed invoice amount due: {invoice.amount_due}'}
                )
            
        except Invoice.DoesNotExist:
            raise serializers.ValidationError(
                {'invoice_id': 'Invoice not found or not payable'}
            )
        
        return attrs


class PaymentReadSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for reading payment details"""
    invoice_id = serializers.SerializerMethodField()
    restaurant_id = serializers.UUIDField(read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    # Payment details
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(read_only=True)
    gateway = serializers.CharField(read_only=True)
    gateway_display = serializers.CharField(source='get_gateway_display', read_only=True)
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    # Gateway references
    gateway_reference = serializers.CharField(read_only=True, allow_null=True)
    gateway_response = serializers.JSONField(read_only=True)
    
    # Customer information
    customer_phone = serializers.CharField(read_only=True, allow_null=True)
    customer_email = serializers.EmailField(read_only=True, allow_null=True)
    customer_user_id = serializers.UUIDField(source='customer_user.id', read_only=True, allow_null=True)
    
    # Timestamps
    processed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    
    # Allocation info
    allocated_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    unallocated_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice_id', 'restaurant_id', 'restaurant_name',
            'amount', 'currency', 'gateway', 'gateway_display',
            'status', 'status_display', 'gateway_reference', 'gateway_response',
            'customer_phone', 'customer_email', 'customer_user_id',
            'processed_at', 'completed_at', 'allocated_amount', 'unallocated_amount',
            'created_at', 'updated_at'
        ]
    
    def get_invoice_id(self, obj):
        # Get the first invoice from allocations
        allocation = obj.allocations.select_related('invoice').first()
        if allocation:
            return allocation.invoice.id
        return None


class PaymentAllocationSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for payment allocations"""
    invoice_id = serializers.UUIDField(required=True)
    payment_id = serializers.UUIDField(required=True)
    allocated_amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    class Meta:
        model = PaymentAllocation
        fields = [
            'id', 'invoice_id', 'payment_id', 'allocated_amount',
            'allocation_date', 'allocated_by', 'created_at', 'updated_at'
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=PaymentAllocation.objects.all(),
                fields=['invoice_id', 'payment_id']
            )
        ]
    
    def validate(self, attrs):
        # Validate invoice exists
        try:
            invoice = Invoice.objects.get(id=attrs['invoice_id'])
            attrs['invoice'] = invoice
        except Invoice.DoesNotExist:
            raise serializers.ValidationError(
                {'invoice_id': 'Invoice not found'}
            )
        
        # Validate payment exists
        try:
            payment = Payment.objects.get(id=attrs['payment_id'])
            attrs['payment'] = payment
        except Payment.DoesNotExist:
            raise serializers.ValidationError(
                {'payment_id': 'Payment not found'}
            )
        
        # Validate allocation constraints
        if attrs['allocated_amount'] > payment.unallocated_amount:
            raise serializers.ValidationError(
                {'allocated_amount': f'Amount exceeds unallocated payment amount: {payment.unallocated_amount}'}
            )
        
        if attrs['allocated_amount'] > invoice.amount_due:
            raise serializers.ValidationError(
                {'allocated_amount': f'Amount exceeds invoice amount due: {invoice.amount_due}'}
            )
        
        return attrs
    
    def create(self, validated_data):
        return PaymentAllocation.objects.create(**validated_data)


class PaymentAllocationReadSerializer(UUIDSerializerMixin):
    """Serializer for reading payment allocations"""
    invoice_id = serializers.UUIDField(source='invoice.id', read_only=True)
    payment_id = serializers.UUIDField(source='payment.id', read_only=True)
    allocated_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    allocation_date = serializers.DateTimeField(read_only=True)
    allocated_by_id = serializers.UUIDField(source='allocated_by.id', read_only=True, allow_null=True)
    
    # Payment details
    payment_status = serializers.CharField(source='payment.status', read_only=True)
    payment_gateway = serializers.CharField(source='payment.gateway', read_only=True)
    payment_amount = serializers.DecimalField(source='payment.amount', max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = PaymentAllocation
        fields = [
            'id', 'invoice_id', 'payment_id', 'allocated_amount',
            'allocation_date', 'allocated_by_id',
            'payment_status', 'payment_gateway', 'payment_amount'
        ]


class CashPaymentCompletionSerializer(serializers.Serializer):
    """Serializer for completing cash payments"""
    payment_id = serializers.UUIDField(required=True)
    staff_user_id = serializers.UUIDField(required=True)
    
    def validate_payment_id(self, value):
        try:
            payment = Payment.objects.get(
                id=value,
                gateway='CASH',
                status='AWAITING_COLLECTION'
            )
            return payment
        except Payment.DoesNotExist:
            raise serializers.ValidationError(
                'Payment not found, not cash payment, or not awaiting collection'
            )
    
    def validate(self, attrs):
        payment = attrs['payment_id']  # This is now the Payment instance
        
        # Check if payment has allocations
        if not payment.allocations.exists():
            raise serializers.ValidationError(
                {'payment_id': 'Payment has no invoice allocations'}
            )
        
        attrs['payment'] = payment
        return attrs


# ====================== ACCOUNTING SERIALIZERS ======================

class AccountingEntrySerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for accounting entries"""
    restaurant_id = serializers.UUIDField(required=True)
    payment_id = serializers.UUIDField(required=False, allow_null=True)
    invoice_id = serializers.UUIDField(required=False, allow_null=True)
    
    # Double-entry accounting
    debit_account = serializers.CharField(max_length=50, required=True)
    credit_account = serializers.CharField(max_length=50, required=True)
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = serializers.CharField(max_length=3, default='UGX')
    
    # Reference tracking
    reference_type = serializers.ChoiceField(
        choices=[choice[0] for choice in AccountingEntry.REFERENCE_TYPE_CHOICES],
        required=True
    )
    reference_id = serializers.UUIDField(required=True)
    
    # Description
    description = serializers.CharField(required=True)
    internal_note = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = AccountingEntry
        fields = [
            'id', 'restaurant_id', 'payment_id', 'invoice_id',
            'debit_account', 'credit_account', 'amount', 'currency',
            'reference_type', 'reference_id', 'description', 'internal_note',
            'entry_date', 'value_date', 'entry_status', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['entry_status', 'posted_at', 'created_at', 'updated_at']
    
    def validate(self, attrs):
        # Validate restaurant exists
        try:
            Restaurant.objects.get(id=attrs['restaurant_id'])
        except Restaurant.DoesNotExist:
            raise serializers.ValidationError(
                {'restaurant_id': 'Restaurant not found'}
            )
        
        # Validate payment if provided
        if attrs.get('payment_id'):
            try:
                Payment.objects.get(id=attrs['payment_id'])
            except Payment.DoesNotExist:
                raise serializers.ValidationError(
                    {'payment_id': 'Payment not found'}
                )
        
        # Validate invoice if provided
        if attrs.get('invoice_id'):
            try:
                Invoice.objects.get(id=attrs['invoice_id'])
            except Invoice.DoesNotExist:
                raise serializers.ValidationError(
                    {'invoice_id': 'Invoice not found'}
                )
        
        return attrs


class AccountingEntryReadSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for reading accounting entries"""
    restaurant_id = serializers.UUIDField(read_only=True)
    payment_id = serializers.UUIDField(source='payment.id', read_only=True, allow_null=True)
    invoice_id = serializers.UUIDField(source='invoice.id', read_only=True, allow_null=True)
    
    # Double-entry accounting
    debit_account = serializers.CharField(read_only=True)
    credit_account = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)
    
    # Reference tracking
    reference_type = serializers.CharField(read_only=True)
    reference_type_display = serializers.CharField(source='get_reference_type_display', read_only=True)
    reference_id = serializers.UUIDField(read_only=True)
    
    # Status and dates
    entry_status = serializers.CharField(read_only=True)
    entry_status_display = serializers.CharField(source='get_entry_status_display', read_only=True)
    entry_date = serializers.DateField(read_only=True)
    value_date = serializers.DateField(read_only=True)
    posted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    
    # Description
    description = serializers.CharField(read_only=True)
    internal_note = serializers.CharField(read_only=True)
    
    # Created by
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    
    class Meta:
        model = AccountingEntry
        fields = [
            'id', 'restaurant_id', 'payment_id', 'invoice_id',
            'debit_account', 'credit_account', 'amount', 'currency',
            'reference_type', 'reference_type_display', 'reference_id',
            'entry_status', 'entry_status_display', 'entry_date', 'value_date',
            'posted_at', 'description', 'internal_note', 'created_by_id',
            'created_at', 'updated_at'
        ]


# ====================== WALLET SERIALIZERS ======================

class CustomerWalletCreateSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for creating customer wallets"""
    user_id = serializers.UUIDField(required=True)
    restaurant_id = serializers.UUIDField(required=True)
    wallet_type = serializers.ChoiceField(
        choices=[choice[0] for choice in CustomerWallet.WALLET_TYPE_CHOICES],
        default='PREPAID'
    )
    currency = serializers.CharField(max_length=8, default='X-SWIFT')
    is_refundable = serializers.BooleanField(default=True)
    max_balance = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = CustomerWallet
        fields = [
            'id', 'user_id', 'restaurant_id', 'wallet_type', 'currency',
            'is_refundable', 'max_balance', 'created_at', 'updated_at'
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=CustomerWallet.objects.all(),
                fields=['user_id', 'restaurant_id', 'wallet_type']
            )
        ]
    
    def validate(self, attrs):
        # Validate restaurant exists
        try:
            Restaurant.objects.get(id=attrs['restaurant_id'])
        except Restaurant.DoesNotExist:
            raise serializers.ValidationError(
                {'restaurant_id': 'Restaurant not found'}
            )
        
        # Validate max_balance if provided
        if attrs.get('max_balance') is not None and attrs['max_balance'] <= 0:
            raise serializers.ValidationError(
                {'max_balance': 'Maximum balance must be greater than zero'}
            )
        
        return attrs
    
    def create(self, validated_data):
        return CustomerWallet.objects.create(**validated_data)


class CustomerWalletReadSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for reading customer wallet details"""
    user_id = serializers.UUIDField(read_only=True)
    restaurant_id = serializers.UUIDField(read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    # Balance tracking
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # Wallet properties
    wallet_type = serializers.CharField(read_only=True)
    wallet_type_display = serializers.CharField(source='get_wallet_type_display', read_only=True)
    currency = serializers.CharField(read_only=True)
    is_refundable = serializers.BooleanField(read_only=True)
    
    # Limits
    max_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    
    # Status
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    closed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    
    # Computed fields
    can_afford = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)
    is_suspended = serializers.BooleanField(read_only=True)
    is_closed = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = CustomerWallet
        fields = [
            'id', 'user_id', 'restaurant_id', 'restaurant_name',
            'available_balance', 'pending_balance', 'total_balance',
            'wallet_type', 'wallet_type_display', 'currency', 'is_refundable',
            'max_balance', 'status', 'status_display', 'closed_at',
            'can_afford', 'is_active', 'is_suspended', 'is_closed',
            'created_at', 'updated_at'
        ]
    
    def get_can_afford(self, obj):
        # This is a computed field that checks if wallet can afford a certain amount
        # In practice, you'd pass the amount through context
        amount = self.context.get('check_amount', Decimal('0'))
        return obj.can_afford(amount)


class WalletFundsOperationSerializer(serializers.Serializer):
    """Base serializer for wallet operations"""
    user_id = serializers.UUIDField(required=True)
    restaurant_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    reference_type = serializers.CharField(max_length=30, required=True)
    reference_id = serializers.UUIDField(required=True)
    description = serializers.CharField(required=True)
    correlation_id = serializers.UUIDField(required=False, allow_null=True)
    wallet_type = serializers.ChoiceField(
        choices=[choice[0] for choice in CustomerWallet.WALLET_TYPE_CHOICES],
        default='PREPAID'
    )
    
    def validate(self, attrs):
        # Validate wallet exists
        try:
            wallet = CustomerWallet.objects.get(
                user_id=attrs['user_id'],
                restaurant_id=attrs['restaurant_id'],
                wallet_type=attrs['wallet_type']
            )
            attrs['wallet'] = wallet
        except CustomerWallet.DoesNotExist:
            raise serializers.ValidationError(
                {'wallet': 'Wallet not found for the given user, restaurant, and type'}
            )
        
        return attrs


class WalletAddFundsSerializer(WalletFundsOperationSerializer):
    """Serializer for adding funds to wallet"""
    pass


class WalletAuthorizeFundsSerializer(WalletFundsOperationSerializer):
    """Serializer for authorizing funds in wallet"""
    pass


class WalletCaptureFundsSerializer(WalletFundsOperationSerializer):
    """Serializer for capturing authorized funds"""
    pass


class WalletReleaseFundsSerializer(WalletFundsOperationSerializer):
    """Serializer for releasing authorized funds"""
    pass


class WalletRefundSerializer(serializers.Serializer):
    """Serializer for processing refunds to wallet"""
    user_id = serializers.UUIDField(required=True)
    restaurant_id = serializers.UUIDField(required=True)
    refund_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    original_payment_ref = serializers.CharField(required=True)
    wallet_type = serializers.ChoiceField(
        choices=[choice[0] for choice in CustomerWallet.WALLET_TYPE_CHOICES],
        default='PREPAID'
    )
    correlation_id = serializers.UUIDField(required=False, allow_null=True)
    
    def validate(self, attrs):
        # Validate wallet exists
        try:
            wallet = CustomerWallet.objects.get(
                user_id=attrs['user_id'],
                restaurant_id=attrs['restaurant_id'],
                wallet_type=attrs['wallet_type']
            )
            attrs['wallet'] = wallet
        except CustomerWallet.DoesNotExist:
            raise serializers.ValidationError(
                {'wallet': 'Wallet not found for the given user, restaurant, and type'}
            )
        
        return attrs


# ====================== WALLET TRANSACTION SERIALIZERS ======================

class WalletTransactionReadSerializer(UUIDSerializerMixin, TimestampSerializerMixin):
    """Serializer for reading wallet transactions"""
    wallet_id = serializers.UUIDField(source='wallet.id', read_only=True)
    
    # Transaction details
    transaction_type = serializers.CharField(read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    running_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # Reference
    reference_type = serializers.CharField(read_only=True, allow_null=True)
    reference_id = serializers.UUIDField(read_only=True, allow_null=True)
    
    # Status
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    # Metadata
    description = serializers.CharField(read_only=True)
    metadata = serializers.JSONField(read_only=True)
    
    # Processing timestamp
    processed_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'wallet_id', 'transaction_type', 'transaction_type_display',
            'amount', 'running_balance', 'reference_type', 'reference_id',
            'status', 'status_display', 'description', 'metadata',
            'processed_at', 'created_at', 'updated_at'
        ]


# ====================== WEBHOOK SERIALIZERS ======================

class PaymentWebhookSerializer(serializers.Serializer):
    """Serializer for payment webhook data"""
    external_id = serializers.UUIDField(required=True)
    status = serializers.ChoiceField(
        choices=['SUCCESSFUL', 'FAILED', 'PENDING'],
        required=True
    )
    transaction_id = serializers.CharField(required=False, allow_null=True)
    payer_message = serializers.CharField(required=False, allow_null=True)
    gateway = serializers.CharField(required=False, default='MOMO')
    metadata = serializers.JSONField(required=False, default=dict)
    
    def validate_external_id(self, value):
        # Validate payment exists
        try:
            payment = Payment.objects.get(id=value)
            return payment
        except Payment.DoesNotExist:
            raise serializers.ValidationError('Payment not found')


# ====================== UTILITY SERIALIZERS ======================

class PaymentGatewaySerializer(serializers.Serializer):
    """Serializer for available payment gateways"""
    code = serializers.CharField(source='0')
    name = serializers.CharField(source='1')


class InvoiceStatusSerializer(serializers.Serializer):
    """Serializer for invoice status options"""
    code = serializers.CharField(source='0')
    name = serializers.CharField(source='1')


class WalletBalanceSerializer(serializers.Serializer):
    """Serializer for wallet balance response"""
    wallet_type = serializers.CharField()
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    status = serializers.CharField()


# ====================== RESPONSE SERIALIZERS ======================

class InvoiceCreateResponseSerializer(serializers.Serializer):
    """Response serializer for invoice creation"""
    success = serializers.BooleanField()
    invoice_id = serializers.UUIDField(required=False)
    order_id = serializers.UUIDField(required=False)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    error = serializers.CharField(required=False, allow_null=True)


class PaymentInitiationResponseSerializer(serializers.Serializer):
    """Response serializer for payment initiation"""
    success = serializers.BooleanField()
    payment_id = serializers.UUIDField(required=False)
    invoice_id = serializers.UUIDField(required=False)
    status = serializers.CharField(required=False)
    gateway = serializers.CharField(required=False)
    message = serializers.CharField(required=False, allow_null=True)
    requires_staff_action = serializers.BooleanField(required=False)
    error = serializers.CharField(required=False, allow_null=True)


class CashPaymentCompletionResponseSerializer(serializers.Serializer):
    """Response serializer for cash payment completion"""
    success = serializers.BooleanField()
    payment_id = serializers.UUIDField(required=False)
    status = serializers.CharField(required=False)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)


class WalletOperationResponseSerializer(serializers.Serializer):
    """Response serializer for wallet operations"""
    success = serializers.BooleanField()
    wallet_id = serializers.UUIDField(required=False)
    new_balance = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    message = serializers.CharField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
    allowed = serializers.BooleanField(required=False)
    reason = serializers.CharField(required=False, allow_null=True)


# ====================== QUERY PARAM SERIALIZERS ======================

class InvoiceQuerySerializer(serializers.Serializer):
    """Serializer for invoice query parameters"""
    restaurant_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in Invoice.STATUS_CHOICES],
        required=False
    )
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    is_overdue = serializers.BooleanField(required=False)
    is_fully_paid = serializers.BooleanField(required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)


class PaymentQuerySerializer(serializers.Serializer):
    """Serializer for payment query parameters"""
    restaurant_id = serializers.UUIDField(required=False)
    gateway = serializers.ChoiceField(
        choices=[choice[0] for choice in Payment.GATEWAY_CHOICES],
        required=False
    )
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in Payment.STATUS_CHOICES],
        required=False
    )
    customer_user_id = serializers.UUIDField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)
    
    