# tests/test_serializers.py
from local_server.src.apps.payment.serializers_util import ErrorResponseSerializer, PaginatedResponseSerializer, SuccessResponseSerializer
import pytest
import uuid
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError
from unittest.mock import patch, MagicMock

from apps.payment.serializers import *
from apps.payment.models import *
from apps.core.models import Restaurant, User
from apps.order_processing.models import OfflineOrder


# ====================== TEST FACTORIES ======================

class TestDataFactory:
    """Factory for creating test data"""
    
    @staticmethod
    def create_restaurant():
        return Restaurant.objects.create(
            name="Test Restaurant",
            supabase_restaurant_id=str(uuid.uuid4()),
            address={"street": "123 Test St"},
            contact_info={"phone": "555-0100"},
            local_config={},
            is_active=True
        )
    
    @staticmethod
    def create_user(restaurant):
        return User.objects.create(
            email="test@example.com",
            username="testuser",
            restaurant_id=restaurant.id
        )
    
    @staticmethod
    def create_offline_order(restaurant, user=None):
        return OfflineOrder.objects.create(
            restaurant=restaurant,
            local_order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Test Item",
                    "price": "40",
                    "quantity": 2,
                    "total": "80"
                }
            ],
            total_amount=Decimal('80.00'),
            tax_amount=Decimal('1.76'),

            special_instructions="Test instructions",
            order_status='READY',
            sync_status='SYNCED'
            )
    
    @staticmethod
    def create_invoice(order, restaurant):
        return Invoice.objects.create(
            order=order,
            restaurant=restaurant,
            subtotal_amount=Decimal("80.00"),
            tax_amount=Decimal("15.00"),
            service_fee=Decimal("5.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            due_date=timezone.now() + timezone.timedelta(days=1),
            status="ISSUED"
        )
    
    @staticmethod
    def create_payment(restaurant,user, invoice=None,):
        payment = Payment.objects.create(
            restaurant=restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='MOMO',
            customer_phone='256712345678',
            customer_email='test@example.com',
            customer_user=user
        )
        
        if invoice:
            PaymentAllocation.objects.create(
                invoice=invoice,
                payment=payment,
                allocated_amount=Decimal("100.00")
            )
        
        return payment
    
    @staticmethod
    def create_wallet(user, restaurant):
        return CustomerWallet.objects.create(
            user_id=user.id,
            restaurant_id=restaurant.id,
            available_balance=Decimal('1000.00'),
            pending_balance=Decimal('0.00'),
            wallet_type='PREPAID',
            status='ACTIVE',
            currency='UGX'
        )


# ====================== BASE TEST CLASSES ======================

class BaseSerializerTest(TestCase):
    """Base test class for serializer tests"""
    
    def setUp(self):
        self.restaurant = TestDataFactory.create_restaurant()
        self.user = TestDataFactory.create_user(self.restaurant)
        self.order = TestDataFactory.create_offline_order(self.restaurant, self.user)
        self.invoice = TestDataFactory.create_invoice(self.order, self.restaurant)
        self.payment = TestDataFactory.create_payment(self.restaurant, self.user, self.invoice)
        self.wallet = TestDataFactory.create_wallet(self.user, self.restaurant)


# ====================== INVOICE SERIALIZER TESTS ======================
@pytest.mark.django_db
class TestInvoiceCreateSerializer(BaseSerializerTest):
    """Tests for InvoiceCreateSerializer"""
    
    def test_valid_invoice_creation(self):
        """Test valid invoice creation"""
        data = {
            'order_id': str(self.order.id),
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': '80.00',
            'tax_amount': '15.00',
            'service_fee': '5.00',
            'discount_amount': '0.00'
        }
        
        serializer = InvoiceCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        assert 'subtotal_amount' in serializer.validated_data
        # Check calculated total
        validated_data = serializer.validated_data
        self.assertEqual(validated_data['total_amount'], Decimal('100.00'))
        self.assertEqual(validated_data['order'], self.order)
    
    def test_invalid_order_for_restaurant(self):
        """Test validation when order doesn't belong to restaurant"""
        other_restaurant = TestDataFactory.create_restaurant()
        
        data = {
            'order_id': str(self.order.id),
            'restaurant_id': str(other_restaurant.id),
            'subtotal_amount': '80.00',
            'tax_amount': '15.00',
            'service_fee': '5.00',
            'discount_amount': '0.00'
        }
        
        serializer = InvoiceCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('order_id', serializer.errors)
    
    def test_negative_total_amount(self):
        """Test validation when total amount is zero or negative"""
        data = {
            'order_id': str(self.order.id),
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': '50.00',
            'tax_amount': '0.00',
            'service_fee': '0.00',
            'discount_amount': '60.00'  # Makes total negative
        }
        
        serializer = InvoiceCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('subtotal_amount', serializer.errors)

@pytest.mark.django_db   
class TestInvoiceReadSerializer(BaseSerializerTest):
    """Tests for InvoiceReadSerializer"""
    
    def test_invoice_read_serialization(self):
        """Test serialization of invoice for reading"""
        serializer = InvoiceReadSerializer(self.invoice)
        data = serializer.data
        
        # Check required fields exist
        expected_fields = [
            'id', 'order_id', 'restaurant_id', 'restaurant_name',
            'subtotal_amount', 'tax_amount', 'service_fee', 'discount_amount',
            'total_amount', 'amount_paid', 'amount_due', 'is_fully_paid',
            'is_overdue', 'status', 'status_display', 'issue_date', 'due_date',
            'paid_at', 'created_at', 'updated_at'
        ]
        
        for field in expected_fields:
            self.assertIn(field, data)
        
        # Check computed fields
        self.assertEqual(data['amount_due'], '100.00')
        self.assertEqual(data['is_fully_paid'], False)
        self.assertEqual(data['is_overdue'], False)
        self.assertEqual(data['restaurant_name'], self.restaurant.name)
    
    def test_invoice_with_partial_payment(self):
        """Test invoice serialization with partial payment"""
        # Create partial payment
        self.invoice.amount_paid = Decimal('50.00')
        self.invoice.status = 'PARTIALLY_PAID'
        self.invoice.save()
        
        serializer = InvoiceReadSerializer(self.invoice)
        data = serializer.data
        
        self.assertEqual(data['amount_due'], '50.00')
        self.assertEqual(data['is_fully_paid'], False)
        self.assertEqual(data['status'], 'PARTIALLY_PAID')

@pytest.mark.django_db
class TestInvoiceStatusSerializer(BaseSerializerTest):
    """Tests for InvoiceStatusSerializer"""
    
    def test_invoice_status_with_allocations(self, invoice_instance, payment_instance):
        """Test invoice status serialization with payment allocations"""
        # Create allocation for the payment
    
        allocation = PaymentAllocation.objects.create(
            invoice=invoice_instance,
            payment=payment_instance,
            allocated_amount=Decimal('2.00')
        )
        
        serializer = InvoiceStatusSerializer(self.invoice)
        data = serializer.data
        
        # Check allocations exist
        self.assertIn('allocations', data)
        self.assertEqual(len(data['allocations']), 1)
        self.assertEqual(data['allocations'][0]['allocated_amount'], '100.00')
        self.assertEqual(data['allocations'][0]['payment_id'], str(self.payment.id))


# ====================== PAYMENT SERIALIZER TESTS ======================

class TestPaymentInitiateSerializer(BaseSerializerTest):
    """Tests for PaymentInitiateSerializer"""
    
    def test_valid_payment_initiation(self):
        """Test valid payment initiation"""
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH',
            'customer_phone': '+256700000000',
            'customer_email': 'customer@example.com'
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        validated_data = serializer.validated_data
        self.assertEqual(validated_data['invoice'], self.invoice)
        self.assertEqual(validated_data['amount'], self.invoice.total_amount)
        self.assertEqual(validated_data['payment_method'], 'CASH')
    
    def test_payment_with_custom_amount(self):
        """Test payment initiation with custom amount (partial payment)"""
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'WALLET',
            'amount': '50.00'
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['amount'], Decimal('50.00'))
    
    def test_payment_exceeds_invoice_amount(self):
        """Test validation when payment amount exceeds invoice amount due"""
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH',
            'amount': '150.00'  # More than invoice total
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('amount', serializer.errors)
    
    def test_invalid_invoice_status(self):
        """Test payment initiation for non-payable invoice"""
        # Mark invoice as paid
        self.invoice.status = 'PAID'
        self.invoice.save()
        
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH'
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('invoice_id', serializer.errors)
    
    def test_invalid_payment_method(self):
        """Test validation with invalid payment method"""
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'INVALID_GATEWAY'
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('payment_method', serializer.errors)


class TestPaymentReadSerializer(BaseSerializerTest):
    """Tests for PaymentReadSerializer"""
    
    def test_payment_read_serialization(self):
        """Test serialization of payment for reading"""
        # Add customer info
        self.payment.customer_phone = '+256700000000'
        self.payment.customer_user = self.user
        self.payment.save()
        
        serializer = PaymentReadSerializer(self.payment)
        data = serializer.data
        
        # Check required fields
        expected_fields = [
            'id', 'invoice_id', 'restaurant_id', 'restaurant_name',
            'amount', 'currency', 'gateway', 'gateway_display',
            'status', 'status_display', 'customer_phone', 'customer_user_id',
            'allocated_amount', 'unallocated_amount'
        ]
        
        for field in expected_fields:
            self.assertIn(field, data)
        
        # Check computed values
        self.assertEqual(data['invoice_id'], (self.invoice.id))
        self.assertEqual(data['allocated_amount'], '100.00')
        self.assertEqual(data['unallocated_amount'], '0.00')
        self.assertEqual(data['customer_user_id'], str(self.user.id))
    
    def test_payment_without_allocation(self):
        """Test payment serialization without invoice allocation"""
        payment = TestDataFactory.create_payment(self.restaurant, self.user)
        
        serializer = PaymentReadSerializer(payment)
        data = serializer.data
        
        self.assertIsNone(data['invoice_id'])
        self.assertEqual(data['allocated_amount'], '0.00')
        self.assertEqual(data['unallocated_amount'], '100.00')


class TestPaymentAllocationSerializer(BaseSerializerTest):
    """Tests for PaymentAllocationSerializer"""
    
    def test_valid_allocation(self):
        """Test valid payment allocation"""
        # Create unallocated payment
        unallocated_payment = TestDataFactory.create_payment(self.restaurant)
        
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_id': str(unallocated_payment.id),
            'allocated_amount': '50.00'
        }
        
        serializer = PaymentAllocationSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Create allocation
        allocation = serializer.save()
        
        self.assertEqual(allocation.invoice, self.invoice)
        self.assertEqual(allocation.payment, unallocated_payment)
        self.assertEqual(allocation.allocated_amount, Decimal('50.00'))
    
    def test_allocation_exceeds_payment_amount(self):
        """Test allocation that exceeds payment amount"""
        small_payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('10.00'),
            currency='UGX',
            gateway='CASH'
        )
        
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_id': str(small_payment.id),
            'allocated_amount': '50.00'
        }
        
        serializer = PaymentAllocationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('allocated_amount', serializer.errors)
    
    def test_allocation_exceeds_invoice_amount_due(self):
        """Test allocation that exceeds invoice amount due"""
        # Make invoice partially paid
        self.invoice.amount_paid = Decimal('80.00')
        self.invoice.save()
        
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_id': str(self.payment.id),
            'allocated_amount': '30.00'  # Only 20.00 is due
        }
        
        serializer = PaymentAllocationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('allocated_amount', serializer.errors)
    
    def test_duplicate_allocation(self):
        """Test preventing duplicate invoice-payment allocations"""
        # Create existing allocation
        PaymentAllocation.objects.create(
            invoice=self.invoice,
            payment=self.payment,
            allocated_amount=Decimal('50.00')
        )
        
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_id': str(self.payment.id),
            'allocated_amount': '30.00'
        }
        
        serializer = PaymentAllocationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # Should fail due to unique together constraint


class TestCashPaymentCompletionSerializer(BaseSerializerTest):
    """Tests for CashPaymentCompletionSerializer"""
    
    def test_valid_cash_payment_completion(self):
        """Test valid cash payment completion"""
        cash_payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='CASH',
            status='AWAITING_COLLECTION'
        )
        
        # Create allocation
        PaymentAllocation.objects.create(
            invoice=self.invoice,
            payment=cash_payment,
            allocated_amount=Decimal('100.00')
        )
        
        data = {
            'payment_id': str(cash_payment.id),
            'staff_user_id': str(self.user.id)
        }
        
        serializer = CashPaymentCompletionSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Verify payment instance is in validated data
        self.assertEqual(serializer.validated_data['payment'], cash_payment)
    
    def test_invalid_payment_status(self):
        """Test completion for payment not awaiting collection"""
        data = {
            'payment_id': str(self.payment.id),  # Not CASH gateway
            'staff_user_id': str(self.user.id)
        }
        
        serializer = CashPaymentCompletionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('payment_id', serializer.errors)
    
    def test_payment_without_allocations(self):
        """Test completion for payment without invoice allocations"""
        cash_payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='CASH',
            status='AWAITING_COLLECTION'
        )
        
        data = {
            'payment_id': str(cash_payment.id),
            'staff_user_id': str(self.user.id)
        }
        
        serializer = CashPaymentCompletionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('payment_id', serializer.errors)


# ====================== WALLET SERIALIZER TESTS ======================

class TestCustomerWalletCreateSerializer(BaseSerializerTest):
    """Tests for CustomerWalletCreateSerializer"""
    
    def test_valid_wallet_creation(self):
        """Test valid wallet creation"""
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'wallet_type': 'LOYALTY',
            'currency': 'X-SWIFT',
            'is_refundable': True
        }
        
        serializer = CustomerWalletCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        wallet = serializer.save()
        
        self.assertEqual(wallet.user, self.user)
        self.assertEqual(wallet.restaurant, self.restaurant)
        self.assertEqual(wallet.wallet_type, 'LOYALTY')
        self.assertEqual(wallet.status, 'ACTIVE')
    
    def test_duplicate_wallet_prevention(self):
        """Test preventing duplicate wallet creation"""
        # Create existing wallet
        CustomerWallet.objects.create(
            user=self.user,
            restaurant=self.restaurant,
            wallet_type='PREPAID'
        )
        
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'wallet_type': 'PREPAID'  # Same type
        }
        
        serializer = CustomerWalletCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # Should fail due to unique together constraint
    
    def test_invalid_max_balance(self):
        """Test validation for invalid max balance"""
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'wallet_type': 'PREPAID',
            'max_balance': '0.00'  # Invalid - must be > 0
        }
        
        serializer = CustomerWalletCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('max_balance', serializer.errors)


class TestCustomerWalletReadSerializer(BaseSerializerTest):
    """Tests for CustomerWalletReadSerializer"""
    
    def test_wallet_read_serialization(self):
        """Test serialization of wallet for reading"""
        # Add pending balance
        self.wallet.pending_balance = Decimal('100.00')
        self.wallet.save()
        
        serializer = CustomerWalletReadSerializer(self.wallet)
        data = serializer.data
        
        # Check required fields
        expected_fields = [
            'id', 'user_id', 'restaurant_id', 'restaurant_name',
            'available_balance', 'pending_balance', 'total_balance',
            'wallet_type', 'wallet_type_display', 'currency',
            'status', 'status_display', 'can_afford',
            'is_active', 'is_suspended', 'is_closed'
        ]
        
        for field in expected_fields:
            self.assertIn(field, data)
        
        # Check computed values
        self.assertEqual(data['total_balance'], '600.00')  # 500 + 100
        self.assertEqual(data['restaurant_name'], self.restaurant.name)
        self.assertEqual(data['is_active'], True)
        self.assertEqual(data['is_closed'], False)
    
    def test_can_afford_with_context(self):
        """Test can_afford field with amount in context"""
        serializer = CustomerWalletReadSerializer(
            self.wallet,
            context={'check_amount': Decimal('300.00')}
        )
        data = serializer.data
        
        self.assertEqual(data['can_afford'], True)
    
    def test_suspended_wallet_serialization(self):
        """Test serialization of suspended wallet"""
        self.wallet.status = 'SUSPENDED'
        self.wallet.save()
        
        serializer = CustomerWalletReadSerializer(self.wallet)
        data = serializer.data
        
        self.assertEqual(data['status'], 'SUSPENDED')
        self.assertEqual(data['is_active'], False)
        self.assertEqual(data['is_suspended'], True)


class TestWalletFundsOperationSerializer(BaseSerializerTest):
    """Tests for WalletFundsOperationSerializer and subclasses"""
    
    def test_valid_funds_operation(self):
        """Test valid funds operation"""
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'amount': '100.00',
            'reference_type': 'ORDER',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test transaction',
            'wallet_type': 'PREPAID'
        }
        
        serializer = WalletAddFundsSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Verify wallet instance is in validated data
        self.assertEqual(serializer.validated_data['wallet'], self.wallet)
    
    def test_invalid_wallet_type(self):
        """Test operation for non-existent wallet type"""
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'amount': '100.00',
            'reference_type': 'ORDER',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test transaction',
            'wallet_type': 'CREDIT'  # Doesn't exist for this user/restaurant
        }
        
        serializer = WalletAddFundsSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('wallet', serializer.errors)
    
    def test_invalid_amount(self):
        """Test operation with invalid amount"""
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'amount': '0.00',  # Invalid - must be > 0
            'reference_type': 'ORDER',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test transaction',
            'wallet_type': 'PREPAID'
        }
        
        serializer = WalletAddFundsSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('amount', serializer.errors)


class TestWalletRefundSerializer(BaseSerializerTest):
    """Tests for WalletRefundSerializer"""
    
    def test_valid_refund_request(self):
        """Test valid refund request"""
        refund_id = uuid.uuid4()
        
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'refund_id': str(refund_id),
            'amount': '50.00',
            'original_payment_ref': str(self.payment.id),
            'wallet_type': 'PREPAID'
        }
        
        serializer = WalletRefundSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Verify wallet instance is in validated data
        self.assertEqual(serializer.validated_data['wallet'], self.wallet)
        self.assertEqual(serializer.validated_data['refund_id'], refund_id)
    
    def test_refund_with_correlation_id(self):
        """Test refund request with correlation ID"""
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'refund_id': str(uuid.uuid4()),
            'amount': '50.00',
            'original_payment_ref': str(self.payment.id),
            'wallet_type': 'PREPAID',
            'correlation_id': str(uuid.uuid4())
        }
        
        serializer = WalletRefundSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertIn('correlation_id', serializer.validated_data)


# ====================== ACCOUNTING SERIALIZER TESTS ======================

class TestAccountingEntrySerializer(BaseSerializerTest):
    """Tests for AccountingEntrySerializer"""
    
    def test_valid_accounting_entry(self):
        """Test valid accounting entry creation"""
        data = {
            'restaurant_id': str(self.restaurant.id),
            'payment_id': str(self.payment.id),
            'invoice_id': str(self.invoice.id),
            'debit_account': 'cash',
            'credit_account': 'revenue',
            'amount': '100.00',
            'currency': 'UGX',
            'reference_type': 'PAYMENT_RECEIVED',
            'reference_id': str(self.payment.id),
            'description': 'Payment received'
        }
        
        serializer = AccountingEntrySerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_accounting_entry_without_payment_or_invoice(self):
        """Test accounting entry without payment or invoice reference"""
        data = {
            'restaurant_id': str(self.restaurant.id),
            'debit_account': 'cash',
            'credit_account': 'revenue',
            'amount': '100.00',
            'currency': 'UGX',
            'reference_type': 'ADJUSTMENT',
            'reference_id': str(uuid.uuid4()),
            'description': 'Manual adjustment'
        }
        
        serializer = AccountingEntrySerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_invalid_reference_type(self):
        """Test accounting entry with invalid reference type"""
        data = {
            'restaurant_id': str(self.restaurant.id),
            'debit_account': 'cash',
            'credit_account': 'revenue',
            'amount': '100.00',
            'currency': 'UGX',
            'reference_type': 'INVALID_TYPE',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test entry'
        }
        
        serializer = AccountingEntrySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('reference_type', serializer.errors)


# ====================== WEBHOOK SERIALIZER TESTS ======================

class TestPaymentWebhookSerializer(BaseSerializerTest):
    """Tests for PaymentWebhookSerializer"""
    
    def test_valid_webhook_data(self):
        """Test valid webhook data"""
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL',
            'transaction_id': 'TXN123456',
            'payer_message': 'Payment successful',
            'gateway': 'MOMO'
        }
        
        serializer = PaymentWebhookSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Verify payment instance is in validated data
        self.assertEqual(serializer.validated_data['external_id'], self.payment)
    
    def test_webhook_with_metadata(self):
        """Test webhook with metadata"""
        metadata = {
            'timestamp': '2024-01-01T12:00:00Z',
            'device_id': 'DEV001'
        }
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL',
            'metadata': metadata
        }
        
        serializer = PaymentWebhookSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['metadata'], metadata)
    
    def test_invalid_external_id(self):
        """Test webhook with non-existent payment ID"""
        data = {
            'external_id': str(uuid.uuid4()),  # Non-existent payment
            'status': 'SUCCESSFUL'
        }
        
        serializer = PaymentWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('external_id', serializer.errors)
    
    def test_invalid_status(self):
        """Test webhook with invalid status"""
        data = {
            'external_id': str(self.payment.id),
            'status': 'INVALID_STATUS'
        }
        
        serializer = PaymentWebhookSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('status', serializer.errors)


# ====================== QUERY PARAMETER TESTS ======================

class TestQueryParameterSerializers(TestCase):
    """Tests for query parameter serializers"""
    
    def test_invoice_query_serializer(self):
        """Test InvoiceQuerySerializer"""
        data = {
            'restaurant_id': str(uuid.uuid4()),
            'status': 'ISSUED',
            'start_date': '2024-01-01T00:00:00Z',
            'end_date': '2024-01-31T23:59:59Z',
            'is_overdue': True,
            'page': 1,
            'page_size': 50
        }
        
        serializer = InvoiceQuerySerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test default values
        data = {'page': 2}
        serializer = InvoiceQuerySerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['page_size'], 20)
    
    def test_payment_query_serializer(self):
        """Test PaymentQuerySerializer"""
        data = {
            'restaurant_id': str(uuid.uuid4()),
            'gateway': 'CASH',
            'status': 'COMPLETED',
            'customer_user_id': str(uuid.uuid4()),
            'page': 1,
            'page_size': 30
        }
        
        serializer = PaymentQuerySerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_invalid_page_number(self):
        """Test validation for invalid page number"""
        data = {'page': 0}  # Must be >= 1
        
        serializer = InvoiceQuerySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('page', serializer.errors)
    
    def test_invalid_page_size(self):
        """Test validation for invalid page size"""
        data = {'page_size': 200}  # Exceeds max of 100
        
        serializer = InvoiceQuerySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('page_size', serializer.errors)


# ====================== RESPONSE SERIALIZER TESTS ======================

class TestResponseSerializers(TestCase):
    """Tests for response serializers"""
    
    def test_invoice_create_response(self):
        """Test InvoiceCreateResponseSerializer"""
        invoice_id = uuid.uuid4()
        order_id = uuid.uuid4()
        
        data = {
            'success': True,
            'invoice_id': invoice_id,
            'order_id': order_id,
            'total_amount': '100.00',
            'amount_due': '100.00'
        }
        
        serializer = InvoiceCreateResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test error response
        data = {
            'success': False,
            'error': 'Invoice creation failed'
        }
        
        serializer = InvoiceCreateResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_payment_initiation_response(self):
        """Test PaymentInitiationResponseSerializer"""
        data = {
            'success': True,
            'payment_id': uuid.uuid4(),
            'invoice_id': uuid.uuid4(),
            'status': 'PENDING',
            'gateway': 'CASH',
            'requires_staff_action': True
        }
        
        serializer = PaymentInitiationResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_wallet_operation_response(self):
        """Test WalletOperationResponseSerializer"""
        data = {
            'success': True,
            'wallet_id': uuid.uuid4(),
            'new_balance': '600.00',
            'available_balance': '500.00',
            'pending_balance': '100.00',
            'message': 'Funds added successfully'
        }
        
        serializer = WalletOperationResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test error response with allowed field
        data = {
            'success': False,
            'allowed': False,
            'reason': 'WALLET_SUSPENDED',
            'message': 'Wallet services are temporarily suspended.'
        }
        
        serializer = WalletOperationResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())


# ====================== UTILITY SERIALIZER TESTS ======================

class TestUtilitySerializers(TestCase):
    """Tests for utility serializers"""
    
    def test_error_response_serializer(self):
        """Test ErrorResponseSerializer"""
        data = {
            'success': False,
            'error': 'Validation failed',
            'error_code': 'VALIDATION_ERROR',
            'details': {'field': 'amount'},
            'correlation_id': str(uuid.uuid4())
        }
        
        serializer = ErrorResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_success_response_serializer(self):
        """Test SuccessResponseSerializer"""
        data = {
            'success': True,
            'message': 'Operation completed successfully',
            'data': {'invoice_id': str(uuid.uuid4())},
            'correlation_id': str(uuid.uuid4())
        }
        
        serializer = SuccessResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_paginated_response_serializer(self):
        """Test PaginatedResponseSerializer"""
        data = {
            'count': 100,
            'next': 'http://example.com/api/invoices/?page=2',
            'previous': None,
            'results': [{'id': str(uuid.uuid4()), 'status': 'ISSUED'}]
        }
        
        serializer = PaginatedResponseSerializer(data=data)
        self.assertTrue(serializer.is_valid())


# ====================== INTEGRATION TESTS ======================

class TestSerializerIntegration(APITestCase):
    """Integration tests for serializers"""
    
    def setUp(self):
        self.restaurant = TestDataFactory.create_restaurant()
        self.user = TestDataFactory.create_user()
        self.client.force_authenticate(user=self.user)
    
    def test_end_to_end_invoice_creation_flow(self):
        """Test complete invoice creation flow"""
        # Create order
        order = TestDataFactory.create_offline_order(self.restaurant, self.user)
        
        # Create invoice
        invoice_data = {
            'order_id': str(order.id),
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': '80.00',
            'tax_amount': '15.00',
            'service_fee': '5.00',
            'discount_amount': '0.00'
        }
        
        invoice_serializer = InvoiceCreateSerializer(data=invoice_data)
        self.assertTrue(invoice_serializer.is_valid())
        invoice = invoice_serializer.save()
        
        # Create payment
        payment_data = {
            'invoice_id': str(invoice.id),
            'payment_method': 'CASH',
            'customer_phone': '+256700000000'
        }
        
        payment_serializer = PaymentInitiateSerializer(data=payment_data)
        self.assertTrue(payment_serializer.is_valid())
        
        # Create allocation
        payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='CASH',
            status='AWAITING_COLLECTION'
        )
        
        allocation_data = {
            'invoice_id': str(invoice.id),
            'payment_id': str(payment.id),
            'allocated_amount': '100.00'
        }
        
        allocation_serializer = PaymentAllocationSerializer(data=allocation_data)
        self.assertTrue(allocation_serializer.is_valid())
        allocation = allocation_serializer.save()
        
        # Verify allocation
        self.assertEqual(allocation.invoice, invoice)
        self.assertEqual(allocation.payment, payment)
        
        # Read invoice status
        status_serializer = InvoiceStatusSerializer(invoice)
        status_data = status_serializer.data
        
        self.assertEqual(len(status_data['allocations']), 1)
        self.assertEqual(status_data['allocations'][0]['payment_id'], str(payment.id))


# ====================== EDGE CASE TESTS ======================

class TestEdgeCases(BaseSerializerTest):
    """Tests for edge cases"""
    
    def test_large_amounts(self):
        """Test serializers with very large amounts"""
        # Maximum 12 digits, 2 decimal places
        large_amount = '9999999999.99'  # 10 billion minus 1 cent
        
        data = {
            'order_id': str(self.order.id),
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': large_amount,
            'tax_amount': '0.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        serializer = InvoiceCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test amount exceeding max digits
        invalid_amount = '100000000000.00'  # 13 digits
        
        data['subtotal_amount'] = invalid_amount
        serializer = InvoiceCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('subtotal_amount', serializer.errors)
    
    def test_special_characters_in_description(self):
        """Test serializers with special characters"""
        description = "Test with special chars: @#$%^&*()_+{}|:\"<>?~`[]\\;',./"
        
        data = {
            'user_id': str(self.user.id),
            'restaurant_id': str(self.restaurant.id),
            'amount': '100.00',
            'reference_type': 'ORDER',
            'reference_id': str(uuid.uuid4()),
            'description': description,
            'wallet_type': 'PREPAID'
        }
        
        serializer = WalletAddFundsSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_unicode_characters(self):
        """Test serializers with unicode characters"""
        description = "Payment for café visit 🍕🎉 テスト"
        
        data = {
            'restaurant_id': str(self.restaurant.id),
            'debit_account': 'cash',
            'credit_account': 'revenue',
            'amount': '100.00',
            'currency': 'UGX',
            'reference_type': 'PAYMENT_RECEIVED',
            'reference_id': str(uuid.uuid4()),
            'description': description
        }
        
        serializer = AccountingEntrySerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_empty_strings_for_optional_fields(self):
        """Test handling of empty strings for optional fields"""
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH',
            'customer_phone': '',  # Empty string
            'customer_email': ''   # Empty string
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        # Should convert to None
        self.assertIsNone(serializer.validated_data.get('customer_phone'))
        self.assertIsNone(serializer.validated_data.get('customer_email'))


# ====================== PERFORMANCE TESTS ======================

class TestPerformance(TestCase):
    """Performance tests for serializers"""
    
    def setUp(self):
        self.restaurant = TestDataFactory.create_restaurant()
        self.user = TestDataFactory.create_user()
        self.invoices = []
        
        # Create 100 invoices for testing
        for i in range(100):
            order = TestDataFactory.create_offline_order(self.restaurant, self.user)
            invoice = TestDataFactory.create_invoice(order, self.restaurant)
            self.invoices.append(invoice)
    
    def test_serializer_performance(self):
        """Test serializer performance with many objects"""
        import time
        
        start_time = time.time()
        
        # Serialize 100 invoices
        serializer = InvoiceReadSerializer(self.invoices, many=True)
        data = serializer.data
        
        end_time = time.time()
        
        # Should complete within reasonable time
        self.assertLess(end_time - start_time, 1.0)  # Less than 1 second
        self.assertEqual(len(data), 100)
    
    def test_nested_serializer_performance(self):
        """Test performance with nested relationships"""
        # Create payments and allocations for all invoices
        payments = []
        for invoice in self.invoices:
            payment = TestDataFactory.create_payment(self.restaurant, invoice)
            payments.append(payment)
        
        import time
        start_time = time.time()
        
        # Serialize payments with nested invoice info
        serializer = PaymentReadSerializer(payments, many=True)
        data = serializer.data
        
        end_time = time.time()
        
        self.assertLess(end_time - start_time, 2.0)  # Less than 2 seconds
        self.assertEqual(len(data), 100)


# ====================== MOCK TESTS ======================

class TestSerializerWithMocks(TestCase):
    """Tests using mocks for external dependencies"""
    
    @patch('apps.payment.serializers.Invoice.objects.get')
    def test_serializer_with_mocked_queryset(self, mock_get):
        """Test serializer with mocked database call"""
        # Setup mock
        mock_invoice = MagicMock()
        mock_invoice.id = uuid.uuid4()
        mock_invoice.total_amount = Decimal('100.00')
        mock_invoice.amount_due = Decimal('100.00')
        mock_invoice.status = 'ISSUED'
        mock_get.return_value = mock_invoice
        
        data = {
            'invoice_id': str(mock_invoice.id),
            'payment_method': 'CASH'
        }
        
        serializer = PaymentInitiateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Verify mock was called
        mock_get.assert_called_once()
    
    @patch('apps.payment.serializers.Restaurant.objects.get')
    def test_serializer_with_invalid_restaurant_mock(self, mock_get):
        """Test serializer when restaurant doesn't exist"""
        # Setup mock to raise DoesNotExist
        from django.core.exceptions import ObjectDoesNotExist
        mock_get.side_effect = ObjectDoesNotExist
        
        data = {
            'restaurant_id': str(uuid.uuid4()),
            'debit_account': 'cash',
            'credit_account': 'revenue',
            'amount': '100.00',
            'reference_type': 'PAYMENT_RECEIVED',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test entry'
        }
        
        serializer = AccountingEntrySerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('restaurant_id', serializer.errors)

# ====================== END OF TESTS ======================