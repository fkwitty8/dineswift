import uuid
from django.db import models
from django.db.models import JSONField
from django.core.validators import MinValueValidator
from apps.core.models import TimeStampedModel
from django.utils import timezone
from decimal import Decimal

from django.db import models, transaction

# Import custom exceptions and WalletTransaction model here
from .exceptions import InsufficientFundsError, MaxBalanceExceededError,RefundError, InactiveWalletError, InvalidPendingCaptureError,InvalidAmountError

from apps.core.models import ActivityLog


class Invoice(TimeStampedModel):
    """Invoice representing the bill for an order"""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
        ('REFUNDED', 'Refunded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        'order_processing.OfflineOrder', 
        on_delete=models.CASCADE,
        related_name='invoice'
    )
    restaurant = models.ForeignKey('core.Restaurant', on_delete=models.CASCADE)
    
    # Amount breakdown
    subtotal_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    tax_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    service_fee = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    discount_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    total_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    
    # Payment tracking
    amount_paid = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Timestamps
    issue_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    
    #invoice metat data for exceptional condition where payment had not invoice
    metadata=JSONField(null=True)
    
    class Meta:
        db_table = 'invoices'
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['restaurant', 'status']),
            models.Index(fields=['due_date']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Invoice {self.id} - {self.get_status_display()}"
    
    @property
    def amount_due(self):
        return self.total_amount - self.amount_paid
    
    @property
    def is_fully_paid(self):
        return self.amount_paid >= self.total_amount
    
    def mark_paid(self, amount=None):
        """Mark invoice as paid or partially paid"""
        payment_amount = amount or self.amount_due
        self.amount_paid += payment_amount
        
        if self.amount_paid >= self.total_amount:
            self.status = 'PAID'
            self.paid_at = timezone.now()
        elif self.amount_paid > 0:
            self.status = 'PARTIALLY_PAID'
        
        self.save()
        
        # Log the payment application to invoice
        ActivityLog.objects.create(
            level='INFO',
            module='INVOICE',
            action='INVOICE_PAYMENT_APPLIED',
            restaurant_id=self.restaurant_id,
            details={
                'invoice_id': str(self.id),
                'order_id': str(self.order.id),
                'payment_amount': float(payment_amount),
                'new_amount_paid': float(self.amount_paid),
                'new_status': self.status
            }
        )
    
    @property
    def is_overdue(self):
        return self.status == 'ISSUED' and timezone.now() > self.due_date
    
class Payment(TimeStampedModel):
    """Payment attempt/transaction - can cover multiple invoices"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
        ('AWAITING_COLLECTION', 'Awaiting Collection'),
    ]
    
    GATEWAY_CHOICES = [
        ('MOMO', 'Mobile Money'),
        ('VISA', 'Visa'),
        ('MASTERCARD', 'Mastercard'),
        ('CASH', 'Cash'),
        ('CRYPTO', 'Cryptocurrency'),
        ('WALLET', 'Customer Wallet'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey('core.Restaurant', on_delete=models.CASCADE)
    
    # Payment details
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    currency = models.CharField(max_length=3, default='UGX')
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Gateway references
    gateway_reference = models.CharField(max_length=255, blank=True, null=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Customer information
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    customer_user = models.ForeignKey(
        'core.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Timing
    processed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Error handling
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'payments'
        indexes = [
            models.Index(fields=['restaurant', 'status']),
            models.Index(fields=['gateway_reference']),
            models.Index(fields=['customer_user', 'created_at']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment {self.id} - {self.get_status_display()}"
    
    def mark_processing(self):
        self.status = 'PROCESSING'
        self.processed_at = timezone.now()
        self.save()
    
    def mark_completed(self, gateway_reference=None, response_data=None):
        """Mark payment as completed and trigger accounting"""
        self.status = 'COMPLETED'
        self.gateway_reference = gateway_reference
        self.gateway_response = response_data or {}
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message):
        self.status = 'FAILED'
        self.error_message = error_message
        self.retry_count += 1
        self.save()
    
    @property
    def allocated_amount(self):
        """Total amount allocated to invoices"""
        return self.allocations.aggregate(
            total=models.Sum('allocated_amount')
        )['total'] or 0
    
    @property
    def unallocated_amount(self):
        """Amount not yet allocated to any invoice"""
        return self.amount - self.allocated_amount
    
    def allocate_to_invoice(self, invoice, amount, allocated_by=None):
        """Allocate payment amount to a specific invoice"""
        if amount <= 0:
            raise ValueError("Allocation amount must be positive")
        
        if amount > self.unallocated_amount:
            raise ValueError("Allocation amount exceeds unallocated payment amount")
        
        if amount > invoice.amount_due:
            raise ValueError("Allocation amount exceeds invoice amount due")
        
        # Create allocation
        allocation = PaymentAllocation.objects.create(
            invoice=invoice,
            payment=self,
            allocated_amount=amount,
            allocated_by=allocated_by
        )
        
        # Update invoice status
        invoice.mark_paid(amount)
        
        return allocation

class PaymentAllocation(TimeStampedModel):
    """Links payments to invoices (many-to-many) with allocation amounts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='allocations')
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='allocations')
    allocated_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    allocation_date = models.DateTimeField(default=timezone.now)
    allocated_by = models.ForeignKey(
        'core.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        db_table = 'payment_allocations'
        unique_together = ['invoice', 'payment']
        indexes = [
            models.Index(fields=['invoice', 'payment']),
            models.Index(fields=['payment', 'invoice']),
        ]
    
    def __str__(self):
        return f"Allocation {self.allocated_amount} from {self.payment} to {self.invoice}"
    
    def save(self, *args, **kwargs):
        """Validate allocation constraints"""
        if self.allocated_amount > self.payment.unallocated_amount:
            raise ValueError("Allocation amount would exceed payment unallocated amount")
        
        if self.allocated_amount > self.invoice.amount_due:
            raise ValueError("Allocation amount would exceed invoice amount due")
        
        super().save(*args, **kwargs)

class AccountingEntry(TimeStampedModel):
    """Double-entry accounting records"""
    ENTRY_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('POSTED', 'Posted'),
        ('VOID', 'Void'),
        ('REVERSED', 'Reversed'),
    ]
    
    REFERENCE_TYPE_CHOICES = [
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('INVOICE_ALLOCATION', 'Invoice Allocation'),
        ('REFUND', 'Refund'),
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('ADJUSTMENT', 'Adjustment'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey('core.Restaurant', on_delete=models.CASCADE)
    payment = models.ForeignKey(
        Payment, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='accounting_entries'
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='accounting_entries'
    )
    
    # Double-entry accounting
    debit_account = models.CharField(max_length=50)
    credit_account = models.CharField(max_length=50)
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    currency = models.CharField(max_length=3, default='UGX')
    
    # Reference tracking
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPE_CHOICES)
    reference_id = models.UUIDField()
    
    # Status and dates
    entry_status = models.CharField(max_length=20, choices=ENTRY_STATUS_CHOICES, default='PENDING')
    entry_date = models.DateField(default=timezone.now)
    value_date = models.DateField(default=timezone.now)
    posted_at = models.DateTimeField(null=True, blank=True)
    
    # Description
    description = models.TextField()
    internal_note = models.TextField(blank=True)
    
    # Adding created_by for audit trail
    created_by = models.UUIDField(null=True, blank=True)
    
    class Meta:
        db_table = 'accounting_entries'
        indexes = [
            models.Index(fields=['restaurant', 'entry_date']),
            models.Index(fields=['reference_type', 'reference_id']),
            models.Index(fields=['debit_account', 'credit_account']),
            models.Index(fields=['entry_status']),
        ]
        ordering = ['-entry_date', '-created_at']
    
    def __str__(self):
        return f"Accounting Entry - {self.debit_account}/{self.credit_account} - {self.amount}"

class CustomerWallet(TimeStampedModel):
    """Customer wallet for prepaid accounts and loyalty"""
    WALLET_TYPE_CHOICES = [
        ('LOYALTY', 'Loyalty'),
        ('PREPAID', 'Prepaid'),
        ('CREDIT', 'Credit'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('CLOSED', 'Closed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('core.User', on_delete=models.CASCADE)
    restaurant = models.ForeignKey('core.Restaurant', on_delete=models.CASCADE)
    
    # Balance tracking
    available_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    pending_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Wallet properties
    wallet_type = models.CharField(max_length=20, choices=WALLET_TYPE_CHOICES, default='LOYALTY')
    currency = models.CharField(max_length=8, default='X-SWIFT')
    is_refundable = models.BooleanField(default=True)
    
    # Limits
    max_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True, 
        blank=True
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    closed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'customer_wallets'
        unique_together = ['user', 'restaurant', 'wallet_type']
        indexes = [
            models.Index(fields=['user', 'restaurant']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Wallet {self.id} - {self.user} - {self.get_wallet_type_display()}"
    
    @property
    def total_balance(self):
        return self.available_balance + self.pending_balance
    
    def can_afford(self, amount):
        return self.available_balance >= amount and self.status == 'ACTIVE'
    
    def is_active(self):
        return self.status == 'ACTIVE'
    
    def is_suspended(self): 
        return self.status == 'SUSPENDED'   
    
    def is_closed(self):
        return self.status == 'CLOSED'
    
    @transaction.atomic
    def authorize_funds(self, amount: Decimal, reference_type: str, reference_id: str, description: str):
        """
        Reserves funds by moving them from available_balance to pending_balance.
        Creates an AUTHORIZATION transaction record.
        """
        # Enforcing business rules using helper functions
        if self.is_suspended():
            # Prevent any new transaction, even if funds are available
            raise InactiveWalletError("Wallet is suspended and cannot process new authorizations.")
        
        if self.is_closed():
            # Prevent any transaction
            raise InactiveWalletError("Wallet is permanently closed.")
            
        if not self.is_active():
            # Catch any other non-active state (or just use the first two checks)
            raise InactiveWalletError("Wallet is not active.")
            
        if not self.can_afford(amount): # can_afford checks available_balance and status
            # Raise custom exception for service layer to catch
            raise InsufficientFundsError("Insufficient funds or wallet inactive for authorization.")
        
        if amount <= Decimal('0'):
            raise InvalidAmountError("Authorization amount must be positive.")

        # Update Balances
        self.available_balance -= amount
        self.pending_balance += amount
        self.save(update_fields=['available_balance', 'pending_balance'])
        
        # Create Transaction Log (Authorization - Net change is 0 on available balance)
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='AUTHORIZATION',
            amount=amount, # Amount reserved
            running_balance=self.available_balance, # Use available balance as reference
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Funds reserved for {description}"
        )
        return True

    @transaction.atomic
    def capture_funds(self, amount: Decimal, reference_type: str, reference_id: str, description: str):
        """
        Finalizes an authorized transaction by removing the amount from pending_balance.
        Creates a CAPTURE transaction record (final deduction).
        """
        if self.status != 'ACTIVE':
            raise InactiveWalletError("Cannot capture funds: wallet is inactive.")
            
        if self.pending_balance < amount:
            # Raise custom exception
            raise InvalidPendingCaptureError(f"Capture amount {amount} exceeds pending balance {self.pending_balance}.")
        
        #  Update Balances
        # Funds were already deducted from available in authorize_funds.
        # We only need to remove the pending hold.
        self.pending_balance -= amount
        self.save(update_fields=['pending_balance'])
    
        # Create Transaction Log (Capture)
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='CAPTURE',
            amount=-amount, # Captured amount is a negative entry against the wallet
            running_balance=self.available_balance, # Available balance remains the same as after Auth
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Funds captured for {description}"
        )
        return True

    @transaction.atomic
    def release_funds(self, amount: Decimal, reference_type: str, reference_id: str, description: str):
        """
        Releases reserved funds back to the available_balance (e.g., cancelled order).
        Creates a RELEASE transaction record.
        """
        if self.status != 'ACTIVE':
            raise InactiveWalletError("Cannot release funds: wallet is inactive.")
            
        if self.pending_balance < amount:
            # Raise custom exception
            raise InvalidPendingCaptureError(f"Release amount {amount} exceeds pending balance {self.pending_balance}.")

        # Update Balances: available up, pending down
        self.available_balance += amount
        self.pending_balance -= amount
        self.save(update_fields=['available_balance', 'pending_balance'])
        
        # Create Transaction Log (Release - Positive movement into available)
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='RELEASE',
            amount=amount, # Amount released
            running_balance=self.available_balance, # Final available balance after release
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Reserved funds released for {description}"
        )
        return True
        
    def deduct_funds(self, amount, reference_type, reference_id, description):
        """Deduct funds from wallet and create transaction"""
        if not self.can_afford(amount):
            raise ValueError("Insufficient funds or wallet inactive")
        
        self.available_balance -= amount
        self.save()
        
        # Create wallet transaction
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='PAYMENT',
            amount=-amount,
            running_balance=self.available_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description
        )
        
        return True
        
    def add_funds(self, amount, reference_type, reference_id, description):
        """Add funds to wallet and create transaction"""
        if amount <= 0:
            raise RefundError("Amount must be positive")
        
        new_balance = self.available_balance + amount
    
        # Check the wallet have a maximum limit defined?
        if self.max_balance is not None and self.max_balance > Decimal('0'):
            # Check  the new balance exceed that limit?
            if new_balance > self.max_balance:
                raise MaxBalanceExceededError(
                    f"Deposit of {amount} would result in a balance of {new_balance}, "
                    f"exceeding the maximum limit of {self.max_balance}."
                )
                
        self.available_balance = new_balance
        self.save(update_fields=['available_balance'])
        
        # Create wallet transaction
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='DEPOSIT',
            amount=amount,
            running_balance=self.available_balance,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description
        )
        
        return True

    @transaction.atomic
    def refund_funds(self, amount: Decimal, original_reference_id: str, description: str):
        """
        Adds funds back to the available_balance and creates a REFUND transaction./used for 
        """
        if amount <= Decimal('0'):
            raise ValueError("Refund amount must be positive.")

        # temprary new Balances: 
        new_balance = self.available_balance + amount
    
        # Check the wallet have a maximum limit defined?
        if self.max_balance is not None and self.max_balance > Decimal('0'):
            # Check  the new balance exceed that limit?
            if new_balance > self.max_balance:
                raise MaxBalanceExceededError(
                    f"Deposit of {amount} would result in a balance of {new_balance}, "
                    f"exceeding the maximum limit of {self.max_balance}."
                )
                
        self.available_balance = new_balance
        self.save(update_fields=['available_balance'])

        # Create Transaction Log (Refund - Positive entry)
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='REFUND',
            amount=amount, # Positive amount returned to the customer
            running_balance=self.available_balance,
            reference_type='ORDER_REFUND',
            reference_id=original_reference_id,
            description=f"Refund issued for order reference {original_reference_id}: {description}"
        )
        return True



class WalletTransaction(TimeStampedModel):
    """Immutable ledger for wallet transactions"""
    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('PAYMENT', 'Payment'),
        ('REFUND', 'Refund'),
        ('ADJUSTMENT', 'Adjustment'),
        ('EXPIRY', 'Expiry'),
        ('AUTHORIZATION', 'Authorization'),
        ('CAPTURE', 'Capture'),
        ('RELEASE', 'Release'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REVERSED', 'Reversed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(CustomerWallet, on_delete=models.CASCADE, related_name='transactions')
    
    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    running_balance = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Reference
    reference_type = models.CharField(max_length=30, blank=True, null=True)
    reference_id = models.UUIDField(blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED')
    
    # Metadata
    description = models.TextField()
    metadata = JSONField(default=dict, blank=True)
    
    # Processing timestamp
    processed_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'wallet_transactions'
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['reference_type', 'reference_id']),
            models.Index(fields=['transaction_type']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Wallet TX {self.id} - {self.get_transaction_type_display()} - {self.amount}"
