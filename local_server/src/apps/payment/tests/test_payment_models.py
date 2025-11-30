import pytest
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from apps.payment.models import Invoice, Payment, PaymentAllocation, CustomerWallet, AccountingEntry, WalletTransaction

@pytest.mark.django_db
class TestPaymentModels:
    """Unit tests for Payment models"""
    
    def test_invoice_creation(self, test_order, test_restaurant):
        """Test creating Invoice with all fields"""
        invoice = Invoice.objects.create(
            order=test_order,
            restaurant=test_restaurant,
            subtotal_amount=Decimal('100.00'),
            tax_amount=Decimal('18.00'),
            service_fee=Decimal('5.00'),
            discount_amount=Decimal('10.00'),
            total_amount=Decimal('113.00'),
            due_date=timezone.now() + timedelta(days=1)
        )
        
        assert invoice.order == test_order
        assert invoice.restaurant == test_restaurant
        assert invoice.subtotal_amount == Decimal('100.00')
        assert invoice.tax_amount == Decimal('18.00')
        assert invoice.service_fee == Decimal('5.00')
        assert invoice.discount_amount == Decimal('10.00')
        assert invoice.total_amount == Decimal('113.00')
        assert invoice.amount_paid == Decimal('0.00')
        assert invoice.status == 'DRAFT'
        assert invoice.amount_due == Decimal('113.00')
        assert not invoice.is_fully_paid
        assert not invoice.is_overdue
    
    def test_invoice_mark_paid_full(self, invoice_instance):
        """Test marking invoice as fully paid"""
        assert invoice_instance.status == 'DRAFT'
        assert invoice_instance.amount_paid == Decimal('0.00')
        
        invoice_instance.mark_paid()
        
        assert invoice_instance.status == 'PAID'
        assert invoice_instance.amount_paid == invoice_instance.total_amount
        assert invoice_instance.paid_at is not None
        assert invoice_instance.is_fully_paid
    
    def test_invoice_mark_partial_payment(self, invoice_instance):
        """Test marking invoice with partial payment"""
        partial_amount = Decimal('50.00')
        
        invoice_instance.mark_paid(partial_amount)
        
        assert invoice_instance.status == 'PARTIALLY_PAID'
        assert invoice_instance.amount_paid == partial_amount
        assert invoice_instance.amount_due == invoice_instance.total_amount - partial_amount
        assert not invoice_instance.is_fully_paid
    
    def test_payment_creation(self, test_restaurant, test_user):
        """Test creating Payment with all fields"""
        payment = Payment.objects.create(
            restaurant=test_restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='MOMO',
            customer_phone='256712345678',
            customer_email='test@example.com',
            customer_user=test_user
        )
        
        assert payment.restaurant == test_restaurant
        assert payment.amount == Decimal('100.00')
        assert payment.currency == 'UGX'
        assert payment.gateway == 'MOMO'
        assert payment.status == 'PENDING'
        assert payment.customer_phone == '256712345678'
        assert payment.customer_email == 'test@example.com'
        assert payment.customer_user == test_user
        assert payment.retry_count == 0
    
    def test_payment_mark_processing(self, payment_instance):
        """Test marking payment as processing"""
        assert payment_instance.status == 'PENDING'
        assert payment_instance.processed_at is None
        
        payment_instance.mark_processing()
        
        assert payment_instance.status == 'PROCESSING'
        assert payment_instance.processed_at is not None
    
    def test_payment_mark_completed(self, payment_instance):
        """Test marking payment as completed"""
        gateway_ref = 'REF123456'
        response_data = {'transaction_id': 'TXN123'}
        
        payment_instance.mark_completed(
            gateway_reference=gateway_ref,
            response_data=response_data
        )
        
        assert payment_instance.status == 'COMPLETED'
        assert payment_instance.gateway_reference == gateway_ref
        assert payment_instance.gateway_response == response_data
        assert payment_instance.completed_at is not None
    
    def test_payment_mark_failed(self, payment_instance):
        """Test marking payment as failed"""
        error_msg = 'Insufficient funds'
        initial_retry_count = payment_instance.retry_count
        
        payment_instance.mark_failed(error_msg)
        
        assert payment_instance.status == 'FAILED'
        assert payment_instance.error_message == error_msg
        assert payment_instance.retry_count == initial_retry_count + 1
    
    def test_payment_allocation_creation(self, payment_instance, invoice_instance, test_user):
        """Test creating PaymentAllocation"""
        allocation = PaymentAllocation.objects.create(
            invoice=invoice_instance,
            payment=payment_instance,
            allocated_amount=Decimal('50.00'),
            allocated_by=test_user
        )
        
        assert allocation.invoice == invoice_instance
        assert allocation.payment == payment_instance
        assert allocation.allocated_amount == Decimal('50.00')
        assert allocation.allocated_by == test_user
    
    def test_payment_allocation_greater_than_invoicedue_or_unalloctedamount(self, payment_instance, invoice_instance, test_user):
        """Test creating PaymentAllocation"""
                
        #allocate more than unallocated funds
        with pytest.raises(Exception, match="Allocation amount would exceed payment unallocated amount"):
            allocation = PaymentAllocation.objects.create(
                invoice=invoice_instance,
                payment=payment_instance,
                allocated_amount=Decimal('130'),
                allocated_by=test_user
            )
        
        #allocate more than invoice funds
        payment_instance.amount = Decimal('130.00')  # More than wallet balance
        payment_instance.gateway = 'WALLET'
        payment_instance.save()
        
        with pytest.raises(Exception, match="Allocation amount would exceed invoice amount due"):
            allocation = PaymentAllocation.objects.create(
                invoice=invoice_instance,
                payment=payment_instance,
                allocated_amount=Decimal('114'),
                allocated_by=test_user
            )        
    
    def test_payment_allocate_to_invoice(self, payment_instance, invoice_instance, test_user):
        """Test payment allocation to invoice"""
        allocation_amount = Decimal('50.00')
        
        allocation = payment_instance.allocate_to_invoice(
            invoice=invoice_instance,
            amount=allocation_amount,
            allocated_by=test_user
        )
        
        assert allocation.allocated_amount == allocation_amount
        assert invoice_instance.amount_paid == allocation_amount
        assert invoice_instance.status == 'PARTIALLY_PAID'
    
    def test_payment_allocated_amount_property(self, payment_instance, invoice_instance,invoice_second_instance, test_user):
        """Test payment allocated amount calculation"""
        # Create multiple allocations
        PaymentAllocation.objects.create(
            invoice=invoice_instance,
            payment=payment_instance,
            allocated_amount=Decimal('30.00'),
            allocated_by=test_user
        )
        
        PaymentAllocation.objects.create(
            invoice=invoice_second_instance,
            payment=payment_instance,
            allocated_amount=Decimal('20.00'),
            allocated_by=test_user
        )
        
        assert payment_instance.allocated_amount == Decimal('50.00')
        assert payment_instance.unallocated_amount == payment_instance.amount - Decimal('50.00')
    
    def test_multiple_payments_one_invoice_allocated_amount(self, invoice_instance,payment_instance,second_payment_instance, test_user):
        """
        Test allocated amount calculation when two different payments 
        are allocated to the same invoice.
        """
        
        PaymentAllocation.objects.create(
            invoice=invoice_instance,
            payment=payment_instance,
            allocated_amount=Decimal('30.00'),
            allocated_by=test_user
        )
        
        
        PaymentAllocation.objects.create(
            invoice=invoice_instance,
            payment=second_payment_instance,  # Uses the NEW payment, satisfying the unique constraint
            allocated_amount=Decimal('20.00'),
            allocated_by=test_user
        )
        
        # Assertions on the Invoice (total allocated to this invoice)
        # Total allocated to the invoice: 30.00 (from Pmt 1) + 20.00 (from Pmt 2) = 50.00
        

        # Assertions on the Payments (checking their individual allocated amounts)
        
        # Re-fetch or refresh the payment objects to reflect the allocation changes saved to the DB
        payment_instance.refresh_from_db()
        second_payment_instance.refresh_from_db()

        # Check the allocated amount property on the first payment
        assert payment_instance.allocated_amount == Decimal('30.00')
        assert payment_instance.unallocated_amount == Decimal('70.00') # 100.00 - 30.00

        # Check the allocated amount property on the second payment
        assert second_payment_instance.allocated_amount == Decimal('20.00')
        assert second_payment_instance.unallocated_amount == Decimal('30.00') # 50.00 - 20.00
        
    def test_customer_wallet_creation(self, test_user, test_restaurant):
        """Test creating CustomerWallet"""
        wallet = CustomerWallet.objects.create(
            user=test_user,
            restaurant=test_restaurant,
            available_balance=Decimal('100.00'),
            wallet_type='PREPAID',
            currency='UGX'
        )
        
        assert wallet.user == test_user
        assert wallet.restaurant == test_restaurant
        assert wallet.available_balance == Decimal('100.00')
        assert wallet.wallet_type == 'PREPAID'
        assert wallet.currency == 'UGX'
        assert wallet.status == 'ACTIVE'
        assert wallet.total_balance == Decimal('100.00')
    
    def test_customer_wallet_can_afford(self, customer_wallet):
        """Test wallet affordability check"""
        assert customer_wallet.can_afford(Decimal('50.00')) is True
        assert customer_wallet.can_afford(Decimal('150.00')) is False
    
    def test_customer_wallet_deduct_funds(self, customer_wallet):
        """Test deducting funds from wallet"""
        initial_balance = customer_wallet.available_balance
        deduct_amount = Decimal('30.00')
        
        customer_wallet.deduct_funds(
            amount=deduct_amount,
            reference_type='ORDER_PAYMENT',
            reference_id='12345678-1234-5678-1234-567812345678',
            description='Test payment'
        )
        
        assert customer_wallet.available_balance == initial_balance - deduct_amount
        
        # Check that transaction was created
        transaction = WalletTransaction.objects.filter(wallet=customer_wallet).first()
        assert transaction is not None
        assert transaction.amount == -deduct_amount
        assert transaction.transaction_type == 'PAYMENT'
    
    def test_customer_wallet_add_funds(self, customer_wallet):
        """Test adding funds to wallet"""
        initial_balance = customer_wallet.available_balance
        add_amount = Decimal('50.00')
        
        customer_wallet.add_funds(
            amount=add_amount,
            reference_type='DEPOSIT',
            reference_id='12345678-1234-5678-1234-567812345678',
            description='Test deposit'
        )
        
        assert customer_wallet.available_balance == initial_balance + add_amount
        
        # Check that transaction was created
        transaction = WalletTransaction.objects.filter(wallet=customer_wallet).first()
        assert transaction is not None
        assert transaction.amount == add_amount
        assert transaction.transaction_type == 'DEPOSIT'
    
   
    def test_accounting_entry_creation(self, test_restaurant, payment_instance, test_user):
        """Test creating AccountingEntry with created_by"""
        entry = AccountingEntry.objects.create(
            restaurant=test_restaurant,
            payment=payment_instance,
            debit_account='cash',
            credit_account='revenue',
            amount=Decimal('100.00'),
            currency='UGX',
            reference_type='PAYMENT_RECEIVED',
            reference_id=payment_instance.id,
            description='Test accounting entry',
            created_by=test_user 
        )
        
        assert entry.restaurant == test_restaurant
        assert entry.payment == payment_instance
        assert entry.debit_account == 'cash'
        assert entry.credit_account == 'revenue'
        assert entry.amount == Decimal('100.00')
        assert entry.reference_type == 'PAYMENT_RECEIVED'
        assert entry.entry_status == 'PENDING'
        assert entry.created_by == test_user  
    
    def test_wallet_transaction_creation(self, customer_wallet):
        """Test creating WalletTransaction"""
        transaction = WalletTransaction.objects.create(
            wallet=customer_wallet,
            transaction_type='DEPOSIT',
            amount=Decimal('50.00'),
            running_balance=Decimal('150.00'),
            reference_type='MANUAL_DEPOSIT',
            reference_id='12345678-1234-5678-1234-567812345678',
            description='Test deposit transaction'
        )
        
        assert transaction.wallet == customer_wallet
        assert transaction.transaction_type == 'DEPOSIT'
        assert transaction.amount == Decimal('50.00')
        assert transaction.running_balance == Decimal('150.00')
        assert transaction.status == 'COMPLETED'