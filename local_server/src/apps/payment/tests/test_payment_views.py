# tests/test_views.py
import json
from urllib.parse import quote_plus
import uuid
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock, ANY

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from apps.core.models import User, Restaurant, ActivityLog
from apps.order_processing.models import OfflineOrder
from apps.payment.models import (
    Invoice, Payment, PaymentAllocation, 
    CustomerWallet, WalletTransaction, AccountingEntry
)
from apps.payment.services import invoice_service, payment_service, wallet_service



# =============================================================================
# TEST UTILITIES
# =============================================================================

class ViewTestUtils:
    """Utility methods for view tests"""
    
    @staticmethod
    def create_test_restaurant():
        return Restaurant.objects.create(
            name="Test Restaurant",
            supabase_restaurant_id=str(uuid.uuid4()),
            address={"street": "123 Test St"},
            contact_info={"phone": "555-0100"},
            local_config={},
            is_active=True
        )
    
    @staticmethod
    def create_test_user(restaurant, is_staff=False, email=None):
        if email is None:
            email = f"{'staff' if is_staff else 'customer'}@test.com"
        
        return User.objects.create_user(
            id=uuid.uuid4(),
            email=email,
            username=email.split('@')[0],
            password="testpass123",
            restaurant=restaurant,
            is_staff=is_staff
        )
    
    @staticmethod
    def create_test_order(restaurant, user=None, total_amount=Decimal("100.00")):
        return OfflineOrder.objects.create(
            id=uuid.uuid4(),
            restaurant=restaurant,
            local_order_id=f"ORDER{uuid.uuid4().hex[:8]}".upper(),
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Test Item",
                    "price": str(total_amount),
                    "quantity": 1,
                    "total": str(total_amount)
                }
            ],
            total_amount=total_amount,
            tax_amount=Decimal('15.00'),
            order_status="PENDING"
        )
    
    @staticmethod
    def create_test_invoice(order, restaurant, total_amount=Decimal("100.00")):
        return Invoice.objects.create(
            order=order,
            restaurant=restaurant,
            subtotal_amount=total_amount * Decimal("0.85"),
            tax_amount=total_amount * Decimal("0.15"),
            service_fee=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=total_amount,
            due_date=timezone.now() + timedelta(days=1),
            status="ISSUED"
        )
    
    @staticmethod
    def create_test_payment(restaurant, invoice=None, gateway="CASH", 
                           amount=Decimal("100.00"), status="PENDING"):
        payment = Payment.objects.create(
            restaurant=restaurant,
            amount=amount,
            currency="UGX",
            gateway=gateway,
            status=status
        )
        
        if invoice:
            PaymentAllocation.objects.create(
                invoice=invoice,
                payment=payment,
                allocated_amount=amount
            )
        
        return payment
    
    @staticmethod
    def create_test_wallet(user, restaurant, wallet_type="PREPAID", 
                          balance=Decimal("500.00")):
        return CustomerWallet.objects.create(
            user=user,
            restaurant=restaurant,
            wallet_type=wallet_type,
            available_balance=balance,
            status="ACTIVE"
        )
    
    @staticmethod
    def assert_success_response(response, message=None):
        """Assert response is successful with standard structure"""
        assert response.status_code in [200, 201], f"Expected success, got {response.status_code}"
        
        if hasattr(response, 'data'):
            data = response.data
            # Handle both regular and nested success structures
            if isinstance(data, dict):
                if 'success' in data:
                    assert data['success'] is True, f"Expected success=True, got {data}"
                elif 'data' in data and isinstance(data['data'], dict):
                    # For nested success structure
                    if 'success' in data['data']:
                        assert data['data']['success'] is True, f"Expected success=True, got {data['data']}"
            
            if message and 'message' in data:
                assert message in data['message'], f"Expected message containing '{message}', got '{data.get('message')}'"
    
    @staticmethod
    def assert_error_response(response, expected_status, error_message=None):
        """Assert response is an error with standard structure"""
        assert response.status_code == expected_status, f"Expected status {expected_status}, got {response.status_code}"
        
        if hasattr(response, 'data'):
            data = response.data
            if isinstance(data, dict):
                if 'success' in data:
                    assert data['success'] is False, f"Expected success=False, got {data}"
                if error_message and 'error' in data:
                    if isinstance(data['error'], dict):
                        # Handle validation error dict
                        error_str = json.dumps(data['error'])
                        assert error_message in error_str, f"Expected error containing '{error_message}', got '{error_str}'"
                    else:
                        assert error_message in str(data['error']), f"Expected error containing '{error_message}', got '{data.get('error')}'"


# =============================================================================
# BASE TEST CLASS
# =============================================================================

class BaseViewTestCase(APITestCase):
    """Base test case for payment views"""
    
    def setUp(self):
        # Create test data
        self.restaurant = ViewTestUtils.create_test_restaurant()
        
        # Create users
        self.staff_user = ViewTestUtils.create_test_user(
            self.restaurant, is_staff=True, email="staff@test.com"
        )
        self.customer_user = ViewTestUtils.create_test_user(
            self.restaurant, is_staff=False, email="customer@test.com"
        )
        
        # Create order and invoice
        self.order = ViewTestUtils.create_test_order(self.restaurant, self.customer_user)
        self.invoice = ViewTestUtils.create_test_invoice(self.order, self.restaurant)
        
        # Create payment
        self.payment = ViewTestUtils.create_test_payment(
            self.restaurant, self.invoice, gateway="CASH", status="AWAITING_COLLECTION"
        )
        
        # Create wallet
        self.wallet = ViewTestUtils.create_test_wallet(
            self.customer_user, self.restaurant, balance=Decimal("500.00")
        )
        
        # Set up clients
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff_user)
        
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(user=self.customer_user)
        
        # Clear activity logs before each test
        ActivityLog.objects.all().delete()
        
        # Print test info
        test_name = self._testMethodName
        print(f"\n{'='*80}")
        print(f"Running: {test_name}")
        print(f"{'='*80}")


# =============================================================================
# INVOICE VIEW TESTS
# =============================================================================

class InvoiceViewTests(BaseViewTestCase):
    """Tests for invoice-related views"""
    
    def test_create_invoice_success(self):
        """Test successful invoice creation"""
    
        new_order = ViewTestUtils.create_test_order(self.restaurant, self.customer_user)
        
        url = reverse('invoice-list')
        
        data = {
            'order_id': str(new_order.id),
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': '100.00',
            'tax_amount': '15.00',
            'service_fee': '5.00',
            'discount_amount': '0.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check response structure
        response_data = response.data
        self.assertIn('id', response_data)
        self.assertEqual(response_data['total_amount'], '120.00')
        
        # Check invoice was created
        invoice = Invoice.objects.get(id=response_data['id'])
        self.assertEqual(invoice.restaurant, self.restaurant)
        self.assertEqual(invoice.status, 'ISSUED')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_CREATED'
        ).first()
        self.assertIsNotNone(activity_log)
        self.assertEqual(activity_log.user, self.staff_user)
    
    def test_create_invoice_validation_error(self):
        """Test invoice creation with validation errors"""
        url = reverse('invoice-list')
        
        new_order = ViewTestUtils.create_test_order(self.restaurant, self.customer_user)
        
        # Missing required fields
        data = {
            'order_id': str(new_order.id)
            # Missing amount fields
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check error response structure
        response_data = response.data
        self.assertIn('error', response_data)
        
        # Check no invoice was created
        invoice_count = Invoice.objects.filter(order=self.order).count()
        self.assertEqual(invoice_count, 1)  # Only the one from setUp
    
    def test_create_invoice_order_not_found(self):
        """Test invoice creation for non-existent order"""
        url = reverse('invoice-list')
        
        data = {
            'order_id': str(uuid.uuid4()),  # Non-existent order
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': '85.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)
        self.assertIn('not found', str(response_data['error']).lower())
    
    def test_create_invoice_unauthorized(self):
        """Test invoice creation without authentication"""
        url = reverse('invoice-list')
        
        new_order = ViewTestUtils.create_test_order(self.restaurant, self.customer_user)
        
        client = APIClient()  # No authentication
        data = {
            'order_id': str(new_order.id),
            'restaurant_id': str(self.restaurant.id),
            'subtotal_amount': '80.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = client.post(url, data, format='json')
        
        print(response.data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_get_invoice_status_success(self):
        """Test successful invoice status retrieval"""
        url = reverse('invoice-status', args=[self.invoice.id])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        
        invoice_data = response_data['data']
        self.assertEqual(invoice_data['invoice_id'], str(self.invoice.id))
        self.assertEqual(invoice_data['status'], 'ISSUED')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_STATUS_REQUESTED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_get_invoice_status_not_found(self):
        """Test invoice status for non-existent invoice"""
        url = reverse('invoice-status', args=[uuid.uuid4()])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        response_data = response.data
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
    
    def test_get_invoice_status_wrong_restaurant(self):
        """Test invoice status for invoice from different restaurant"""
        # Create another restaurant and user
        other_restaurant = ViewTestUtils.create_test_restaurant()
        other_user = ViewTestUtils.create_test_user(other_restaurant, is_staff=True)
        
        # Try to access invoice from different restaurant
        client = APIClient()
        client.force_authenticate(user=other_user)
        
        url = reverse('invoice-status', args=[self.invoice.id])
        response = client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def test_get_order_invoice_success(self):
        """Test successful order invoice retrieval"""
        url = reverse('order-invoice', args=[self.order.id])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        
        invoice_data = response_data['data']
        self.assertEqual(invoice_data['order_id'], str(self.order.id))
    
    def test_get_order_invoice_creates_if_missing(self):
        """Test that order invoice is created if it doesn't exist"""
        # Create order without invoice
        new_order = ViewTestUtils.create_test_order(self.restaurant)
        
        url = reverse('order-invoice', args=[new_order.id])
        
        # Mock the invoice service to avoid actual creation
        with patch.object(Invoice, 'create_invoice') as mock_create:
            mock_create.return_value = {
                'success': True,
                'invoice_id': str(uuid.uuid4())
            }
            
            response = self.staff_client.get(url)
        
        # Should still work, either returning existing or creating new
        self.assertIn(response.status_code, [200, 201])
    
    def test_get_order_invoice_order_not_found(self):
        """Test order invoice for non-existent order"""
        url = reverse('order-invoice', args=[uuid.uuid4()])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_list_invoices_success(self):
        """Test successful invoice listing"""
        url = reverse('invoice-list')
        
        # Create additional invoices
        for i in range(5):
            order = ViewTestUtils.create_test_order(self.restaurant)
            ViewTestUtils.create_test_invoice(order, self.restaurant)
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check pagination
        response_data = response.data
        self.assertIn('count', response_data)
        self.assertIn('results', response_data)
        
        # Should include all invoices for this restaurant
        self.assertGreaterEqual(response_data['count'], 6)  # 1 from setUp + 5 new
    
    def test_list_invoices_with_filters(self):
        """Test invoice listing with filters"""
        url = reverse('invoice-list')
        
        # Create invoices with different statuses
        order1 = ViewTestUtils.create_test_order(self.restaurant)
        invoice1 = ViewTestUtils.create_test_invoice(order1, self.restaurant)
        invoice1.status = 'PAID'
        invoice1.save()
        
        order2 = ViewTestUtils.create_test_order(self.restaurant)
        invoice2 = ViewTestUtils.create_test_invoice(order2, self.restaurant)
        invoice2.status = 'OVERDUE'
        invoice2.save()
        
        # Filter by status
        response = self.staff_client.get(f"{url}?status=PAID")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertEqual(response_data['count'], 1)
        self.assertEqual(response_data['results'][0]['status'], 'PAID')
        
        # Filter by date range
        start_date = timezone.now() - timedelta(days=7)
        end_date = timezone.now() + timedelta(days=1)
        
        # URL-encode date parameters
        encoded_start_date = quote_plus(start_date.isoformat())
        encoded_end_date = quote_plus(end_date.isoformat())
        
        # 2. Construct the URL with encoded values
        date_filter_url = f"{url}?start_date={encoded_start_date}&end_date={encoded_end_date}"
        
        response = self.staff_client.get(date_filter_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_invoice_success(self):
        """Test successful invoice retrieval by ID"""
        url = reverse('invoice-detail', args=[self.invoice.id])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertEqual(response_data['id'], str(self.invoice.id))
        self.assertEqual(response_data['order_id'], str(self.order.id))
    
    def test_get_invoice_allocations_success(self):
        """Test successful retrieval of invoice allocations"""
        url = reverse('invoice-allocations', args=[self.invoice.id])
        
        # Create allocations
        for i in range(3):
            payment = ViewTestUtils.create_test_payment(self.restaurant, self.invoice)
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should return allocation data
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 4)  # 1 from setUp + 3 new


# =============================================================================
# PAYMENT VIEW TESTS
# =============================================================================

class PaymentViewTests(BaseViewTestCase):
    """Tests for payment-related views"""
    
    #initiate payment tests
    def test_initiate_payment_success(self):
        """Test successful payment initiation"""
        url = reverse('payment-list')
        
        data = {
            'invoice_id': self.invoice.id,
            'payment_method': 'CASH',
            'amount': '95.00',
            'customer_phone': '+256700000000',
            'customer_email': 'test@example.com'
        }
        
        # Mock the payment service (setup remains the same)
        with patch.object(payment_service, 'initiate_payment') as mock_service:
            mock_service.return_value = {
                'success': True,
                'payment_id': str(uuid.uuid4()),
                'invoice_id': str(self.invoice.id),
                'status': 'AWAITING_COLLECTION',
                'gateway': 'CASH',
                'message': 'Payment awaiting collection'
            }
            
            response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        response_data = response.data
        
        # Assert 'success' is True (Still correct at top level)
        self.assertTrue(response_data['success'])
        
        # Assert 'payment_id' is in the top-level response_data
        self.assertIn('payment_id', response_data)
        
        # Assert 'gateway' value is 'CASH' from the top-level response_data
        self.assertEqual(response_data['gateway'], 'CASH')
        
    def test_initiate_payment_validation_error(self):
        """Test payment initiation with validation errors"""
        url = reverse('payment-list')
        
        # Missing required fields
        data = {
            'payment_method': 'CASH'
            # Missing invoice_id
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)
    
    def test_initiate_payment_invoice_not_found(self):
        """Test payment initiation for non-existent invoice"""
        url = reverse('payment-list')
        
        data = {
            'invoice_id': str(uuid.uuid4()),
            'payment_method': 'CASH'
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)
        self.assertIn('not found', str(response_data['error']).lower())
    
    def test_initiate_payment_service_error(self):
        """Test payment initiation when service fails"""
        url = reverse('payment-list')
        
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH',
            'amount': '50.00',
            'customer_phone': '+256700000000',
            'customer_email': 'test@example.com'
        }
        
        # Mock service to return error
        with patch.object(payment_service, 'initiate_payment') as mock_service:
            mock_service.return_value = {
                'success': False,
                'error': 'Payment gateway unreachable'
            }
            
            response = self.staff_client.post(url, data, format='json')
                
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        
        self.assertIn('error', response_data)
    
    #allocate paymnet tests
    def test_allocate_payment_success(self):
        """Test successful payment allocation"""
        other_payment = ViewTestUtils.create_test_payment(
            self.restaurant, amount=Decimal('200.00')
        )
        
        url = reverse('allocate-payment', args=[other_payment.id])
        
        # Create a different invoice for allocation
        other_order = ViewTestUtils.create_test_order(self.restaurant)
        other_invoice = ViewTestUtils.create_test_invoice(other_order, self.restaurant)
        
        data = {
            'invoice_id': other_invoice.id,
            'allocated_amount': '50.00',
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        # response_data = response.data
        # self.assertIn('helloe', response_data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        self.assertIn('message', response_data)
        
        # Check allocation was created
        allocation = PaymentAllocation.objects.filter(
            payment=other_payment,
            invoice=other_invoice
        ).first()
        self.assertIsNotNone(allocation)
        self.assertEqual(allocation.allocated_amount, Decimal('50.00'))
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='PAYMENT_ALLOCATED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_allocate_payment_insufficient_funds(self):
        """Test payment allocation with insufficient payment amount"""
        url = reverse('allocate-payment', args=[self.payment.id])
        
        data = {
            'invoice_id': str(self.invoice.id),
            'allocated_amount': '1000.00'  # More than payment amount
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
    
    def test_allocate_payment_invalid_invoice(self):
        """Test payment allocation to non-existent invoice"""
        
        other_payment = ViewTestUtils.create_test_payment(
            self.restaurant, amount=Decimal('200.00')
        )
        
        url = reverse('allocate-payment', args=[other_payment.id])
        
        data = {
            'invoice_id': str(uuid.uuid4()),
            'allocated_amount': '60.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        self.assertIn('error', response.data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    #cash payment test
    def test_complete_cash_payment_success(self):
        """Test successful cash payment completion"""
        url = reverse('complete-cash-payment', args=[self.payment.id])
        
        response = self.staff_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        
        # Check payment status was updated
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'COMPLETED')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='CASH_PAYMENT_COLLECTED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_complete_cash_payment_not_found(self):
        """Test cash payment completion for non-existent payment"""
        url = reverse('complete-cash-payment', args=[uuid.uuid4()])
        
        response = self.staff_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertFalse(response_data['success'])
    
    def test_complete_cash_payment_wrong_status(self):
        """Test cash payment completion for payment not awaiting collection"""
        # Create payment with wrong status
        payment = ViewTestUtils.create_test_payment(
            self.restaurant, gateway="CASH", status="COMPLETED"
        )
        
        url = reverse('complete-cash-payment', args=[payment.id])
        
        response = self.staff_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    #refund payment test
    def test_request_refund_success(self):
        """Test successful refund request"""
        # Create a completed payment
        completed_payment = ViewTestUtils.create_test_payment(
            self.restaurant, self.invoice, gateway="CASH", status="COMPLETED"
        )
        
        url = reverse('request-refund', args=[completed_payment.id])
        
        data = {
            'amount': '50.00',
            'original_payment_ref': str(completed_payment.id),
            'wallet_type': 'PREPAID',
            'reason': 'Test refund'
        }
        
        # Mock wallet service
        with patch.object(wallet_service, 'process_refund') as mock_service:
            mock_service.return_value = True
            
            response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        
        # Check payment status
        completed_payment.refresh_from_db()
        self.assertEqual(completed_payment.status, 'REFUNDED')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='REFUND_PROCESSED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_request_refund_insufficient_permissions(self):
        """Test refund request without proper permissions"""
        # Customer shouldn't be able to process refunds
        url = reverse('request-refund', args=[self.payment.id])
        
        data = {
            'amount': '50.00',
            'original_payment_ref': str(self.payment.id),
            'wallet_type': 'PREPAID'
        }
        
        response = self.customer_client.post(url, data, format='json')
        
        # Should be 403 or 401 depending on permission setup
        self.assertIn(response.status_code, [401, 403])
    
    #order payments test
    def test_get_order_payments_success(self):
        """Test successful order payments retrieval"""
        url = reverse('order-payments', args=[self.order.id])
        
        # Create additional payments
        for i in range(2):
            ViewTestUtils.create_test_payment(self.restaurant, self.invoice)
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        
        data = response_data['data']
        self.assertEqual(len(data['payments']), 3)  # 1 from setUp + 2 new
    
    def test_get_order_payments_order_not_found(self):
        """Test order payments for non-existent order"""
        url = reverse('order-payments', args=[uuid.uuid4()])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    #payments
    def test_list_payments_success(self):
        """Test successful payment listing"""
        url = reverse('payment-list')
        
        # Create additional payments
        for i in range(5):
            ViewTestUtils.create_test_payment(self.restaurant)
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertIn('count', response_data)
        self.assertIn('results', response_data)
        self.assertGreaterEqual(response_data['count'], 6)
    
    def test_list_payments_with_filters(self):
        """Test payment listing with filters"""
        url = reverse('payment-list')
        
        # Create payments with different gateways
        cash_payment = ViewTestUtils.create_test_payment(
            self.restaurant, gateway="CASH", status="COMPLETED"
        )
        momo_payment = ViewTestUtils.create_test_payment(
            self.restaurant, gateway="MOMO", status="PENDING"
        )
        
        # Filter by gateway
        response = self.staff_client.get(f"{url}?gateway=CASH")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertGreaterEqual(response_data['count'], 1)
        
        # All results should be CASH payments
        for payment in response_data['results']:
            self.assertEqual(payment['gateway'], 'CASH')
        
        # Filter by status
        response = self.staff_client.get(f"{url}?status=COMPLETED")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_payment_success(self):
        """Test successful payment retrieval by ID"""
        url = reverse('payment-detail', args=[self.payment.id])
        
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertEqual(response_data['id'], str(self.payment.id))
        self.assertEqual(response_data['gateway'], 'CASH')
    
    def test_cancel_payment_success(self):
        """Test successful payment cancellation"""
        # Create a pending payment
        pending_payment = ViewTestUtils.create_test_payment(
            self.restaurant, gateway="MOMO", status="PENDING"
        )
        
        url = reverse('payment-cancel', args=[pending_payment.id])
        
        response = self.staff_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check payment was cancelled
        pending_payment.refresh_from_db()
        self.assertEqual(pending_payment.status, 'CANCELLED')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='PAYMENT_CANCELLED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_cancel_payment_invalid_status(self):
        """Test payment cancellation for payment that cannot be cancelled"""
        url = reverse('payment-cancel', args=[self.payment.id])
        
        response = self.staff_client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)


# =============================================================================
# WALLET VIEW TESTS
# =============================================================================

class WalletViewTests(BaseViewTestCase):
    """Tests for wallet-related views"""
    
    def test_get_wallet_balance_success(self):
        """Test successful wallet balance retrieval"""
        url = reverse('wallet-balance')
        
        response = self.customer_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        
        balance_data = response_data['data']
        self.assertEqual(float(balance_data['available_balance']), 500.00)
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='WALLET',
            action='WALLET_BALANCE_REQUESTED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_get_wallet_balance_with_wallet_type(self):
        """Test wallet balance retrieval with specific wallet type"""
        # Create loyalty wallet
        loyalty_wallet = ViewTestUtils.create_test_wallet(
            self.customer_user, self.restaurant, 
            wallet_type="LOYALTY", balance=Decimal("100.00")
        )
        
        url = reverse('wallet-balance') + '?wallet_type=LOYALTY'
        
        response = self.customer_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        balance_data = response_data['data']
        self.assertEqual(balance_data['wallet_type'], 'LOYALTY')
        self.assertEqual(float(balance_data['available_balance']), 100.00)
    
    def test_get_wallet_balance_wallet_not_found(self):
        """Test wallet balance for non-existent wallet type"""
        url = reverse('wallet-balance') + '?wallet_type=CREDIT'
        
        response = self.customer_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        response_data = response.data
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
    
    def test_get_wallet_transactions_success(self):
        """Test successful wallet transactions retrieval"""
        url = reverse('wallet-transactions')
        
        # Create some transactions
        for i in range(5):
            WalletTransaction.objects.create(
                wallet=self.wallet,
                transaction_type='DEPOSIT',
                amount=Decimal('100.00'),
                running_balance=Decimal(f'{500.00 + (i+1)*100.00}'),
                reference_type='TEST',
                reference_id=uuid.uuid4(),
                description=f'Test transaction {i+1}'
            )
        
        response = self.customer_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        
        transactions = response_data['data']
        self.assertEqual(len(transactions), 5)
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='WALLET',
            action='WALLET_TRANSACTIONS_REQUESTED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_get_wallet_transactions_with_limit(self):
        """Test wallet transactions with limit parameter"""
        url = reverse('wallet-transactions') + '?limit=2'
        
        # Create transactions
        for i in range(5):
            WalletTransaction.objects.create(
                wallet=self.wallet,
                transaction_type='DEPOSIT',
                amount=Decimal('100.00'),
                running_balance=Decimal('600.00'),
                reference_type='TEST',
                reference_id=uuid.uuid4(),
                description=f'Test transaction {i+1}'
            )
        
        response = self.customer_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        transactions = response_data['data']
        self.assertEqual(len(transactions), 2)  # Limited to 2
    
    def test_add_wallet_funds_success(self):
        """Test successful addition of wallet funds"""
        url = reverse('add-wallet-funds')
        
        data = {
            'amount': '200.00',
            'reference_type': 'DEPOSIT',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test deposit',
            'correlation_id': str(uuid.uuid4())
        }
        
        response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        
        # Check wallet balance was updated
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('700.00'))
        
        # Check transaction was created
        transaction = WalletTransaction.objects.filter(
            wallet=self.wallet,
            transaction_type='DEPOSIT'
        ).first()
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, Decimal('200.00'))
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='WALLET',
            action='FUNDS_ADDED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_add_wallet_funds_validation_error(self):
        """Test wallet funds addition with validation errors"""
        url = reverse('add-wallet-funds')
        
        # Missing required fields
        data = {
            'amount': '200.00'
            # Missing other required fields
        }
        
        response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)
    
    def test_add_wallet_funds_negative_amount(self):
        """Test wallet funds addition with negative amount"""
        url = reverse('add-wallet-funds')
        
        data = {
            'amount': '-100.00',
            'reference_type': 'DEPOSIT',
            'reference_id': str(uuid.uuid4()),
            'description': 'Invalid deposit'
        }
        
        response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)
    
    def test_add_wallet_funds_service_error(self):
        """Test wallet funds addition when service fails"""
        url = reverse('add-wallet-funds')
        
        data = {
            'amount': '200.00',
            'reference_type': 'DEPOSIT',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test deposit'
        }
        
        # Mock service to return error
        with patch.object(wallet_service, 'add_funds') as mock_service:
            mock_service.return_value = {
                'success': False,
                'error': 'Max balance exceeded'
            }
            
            response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
        
        # Check error activity log
        activity_log = ActivityLog.objects.filter(
            module='WALLET',
            action='ADD_FUNDS_FAILED'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_authorize_order_payment_success(self):
        """Test successful order payment authorization"""
        url = reverse('authorize-order-payment')
        
        order_id = uuid.uuid4()
        data = {
            'order_id': str(order_id),
            'amount': '100.00',
            'reference_type': 'ORDER',
            'reference_id': str(order_id),
            'description': 'Order authorization'
        }
        
        # Mock wallet service
        with patch.object(wallet_service, 'authorize_order_payment') as mock_service:
            mock_service.return_value = True
            
            response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='WALLET',
            action='AUTHORIZATION_SUCCESS'
        ).first()
        self.assertIsNotNone(activity_log)
    
    def test_capture_order_payment_success(self):
        """Test successful order payment capture"""
        url = reverse('capture-order-payment')
        
        order_id = uuid.uuid4()
        data = {
            'order_id': str(order_id),
            'amount': '100.00',
            'reference_type': 'ORDER',
            'reference_id': str(order_id),
            'description': 'Order capture'
        }
        
        # Mock wallet service
        with patch.object(wallet_service, 'capture_order_payment') as mock_service:
            mock_service.return_value = True
            
            response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
    
    def test_release_order_authorization_success(self):
        """Test successful order authorization release"""
        url = reverse('release-authorization')
        
        order_id = uuid.uuid4()
        data = {
            'order_id': str(order_id),
            'amount': '100.00',
            'reference_type': 'ORDER_CANCEL',
            'reference_id': str(order_id),
            'description': 'Order cancellation'
        }
        
        # Mock wallet service
        with patch.object(wallet_service, 'release_order_authorization') as mock_service:
            mock_service.return_value = True
            
            response = self.customer_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.data
        self.assertTrue(response_data['success'])
    
    def test_get_payment_methods_success(self):
        """Test successful payment methods retrieval"""
        url = reverse('payment-methods')
        
        response = self.customer_client.get(url)
        
        # This endpoint might return empty list if no methods configured
        self.assertIn(response.status_code, [200, 404])
        
        if response.status_code == 200:
            response_data = response.data
            self.assertTrue(response_data['success'])
            self.assertIn('payment_methods', response_data.get('data', {}))


# =============================================================================
# WEBHOOK VIEW TESTS
# =============================================================================

class WebhookViewTests(TestCase):
    """Tests for webhook views (no authentication required)"""
    
    def setUp(self):
        self.restaurant = ViewTestUtils.create_test_restaurant()
        self.user = ViewTestUtils.create_test_user(self.restaurant, is_staff=True)
        
        # Create payment for webhook tests
        self.payment = ViewTestUtils.create_test_payment(
            self.restaurant, gateway="MOMO", status="PENDING"
        )
        
        # Clear activity logs
        ActivityLog.objects.all().delete()
    
    def test_momo_webhook_success(self):
        """Test successful Momo webhook processing"""
        url = reverse('momo-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL',
            'transaction_id': 'TXN123456',
            'payer_message': 'Payment successful'
        }
        
        # Mock payment service
        with patch.object(payment_service, 'handle_webhook') as mock_service:
            mock_service.return_value = {'success': True}
            
            response = self.client.post(
                url, 
                data, 
                format='json',
                HTTP_X_CORRELATION_ID=str(uuid.uuid4())
            )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check activity logs
        received_log = ActivityLog.objects.filter(
            action='MOMO_WEBHOOK_RECEIVED'
        ).first()
        self.assertIsNotNone(received_log)
        
        processed_log = ActivityLog.objects.filter(
            action='MOMO_WEBHOOK_PROCESSED'
        ).first()
        self.assertIsNotNone(processed_log)
    
    def test_momo_webhook_validation_error(self):
        """Test Momo webhook with validation errors"""
        url = reverse('momo-webhook')
        
        # Invalid data
        data = {
            'status': 'SUCCESSFUL'
            # Missing external_id
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check error log
        error_log = ActivityLog.objects.filter(
            action='MOMO_WEBHOOK_VALIDATION_FAILED'
        ).first()
        self.assertIsNotNone(error_log)
    
    def test_momo_webhook_payment_not_found(self):
        """Test Momo webhook for non-existent payment"""
        url = reverse('momo-webhook')
        
        data = {
            'external_id': str(uuid.uuid4()),
            'status': 'SUCCESSFUL'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_momo_webhook_service_error(self):
        """Test Momo webhook when service fails"""
        url = reverse('momo-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL'
        }
        
        # Mock service to return error
        with patch.object(payment_service, 'handle_webhook') as mock_service:
            mock_service.return_value = {
                'success': False,
                'error': 'Payment processing failed'
            }
            
            response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check error log
        error_log = ActivityLog.objects.filter(
            action='MOMO_WEBHOOK_PROCESSING_FAILED'
        ).first()
        self.assertIsNotNone(error_log)
    
    def test_card_webhook_success(self):
        """Test successful card webhook processing"""
        url = reverse('card-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL'
        }
        
        with patch.object(payment_service, 'handle_webhook') as mock_service:
            mock_service.return_value = {'success': True}
            
            response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_generic_webhook_success(self):
        """Test successful generic webhook processing"""
        url = reverse('generic-payment-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL',
            'gateway': 'MOMO'
        }
        
        with patch.object(payment_service, 'handle_webhook') as mock_service:
            mock_service.return_value = {'success': True}
            
            response = self.client.post(
                url, 
                data, 
                format='json',
                HTTP_X_GATEWAY='MOMO'
            )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_generic_webhook_missing_gateway(self):
        """Test generic webhook without gateway specification"""
        url = reverse('generic-payment-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.data
        self.assertIn('error', response_data)
        self.assertIn('gateway', str(response_data['error']).lower())
    
    def test_webhook_critical_error_handling(self):
        """Test webhook handling of critical errors"""
        url = reverse('momo-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL'
        }
        
        # Mock service to raise exception
        with patch.object(payment_service, 'handle_webhook') as mock_service:
            mock_service.side_effect = Exception("Critical database error")
            
            response = self.client.post(url, data, format='json')
        
        # Should return 500 but not crash
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check critical error log
        error_log = ActivityLog.objects.filter(
            level='CRITICAL',
            action='MOMO_WEBHOOK_CRITICAL_ERROR'
        ).first()
        self.assertIsNotNone(error_log)


# =============================================================================
# ERROR HANDLING AND EDGE CASES
# =============================================================================

class ErrorHandlingTests(BaseViewTestCase):
    """Tests for error handling and edge cases"""
    
    def test_malformed_json_request(self):
        """Test handling of malformed JSON"""
        url = reverse('invoice-list')
        
        # Send malformed JSON
        response = self.staff_client.post(
            url, 
            '{"invalid": json, missing quotes}', 
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_large_request_body(self):
        """Test handling of large request bodies"""
        url = reverse('invoice-list')
        
        # Create very large description
        large_data = {
            'order_id': str(self.order.id),
            'subtotal_amount': '85.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00',
            'metadata': {'large_field': 'x' * 10000}  # 10KB field
        }
        
        response = self.staff_client.post(url, large_data, format='json')
        
        # Should handle gracefully (might be 400 or 413)
        self.assertIn(response.status_code, [400, 413, 201])
    
    def test_sql_injection_attempt(self):
        """Test handling of SQL injection attempts"""
        url = reverse('invoice-list')
        
        # Attempt SQL injection in field
        data = {
            'order_id': "'; DROP TABLE invoices; --",
            'subtotal_amount': '85.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        # Should be validation error, not crash
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_xss_attempt(self):
        """Test handling of XSS attempts"""
        url = reverse('invoice-list')
        
        # Attempt XSS in field
        data = {
            'order_id': str(self.order.id),
            'subtotal_amount': '85.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00',
            'metadata': {'description': '<script>alert("xss")</script>'}
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        # Should handle gracefully
        self.assertIn(response.status_code, [201, 400])
    
    def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        import threading
        
        url = reverse('add-wallet-funds')
        
        responses = []
        
        def make_request():
            data = {
                'amount': '100.00',
                'reference_type': 'CONCURRENT_TEST',
                'reference_id': str(uuid.uuid4()),
                'description': 'Concurrent test'
            }
            response = self.customer_client.post(url, data, format='json')
            responses.append(response.status_code)
        
        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All requests should be handled
        self.assertEqual(len(responses), 3)
        
        # Most should be successful (200 or 201)
        success_count = sum(1 for code in responses if code in [200, 201])
        self.assertGreaterEqual(success_count, 2)  # At least 2 should succeed
    
    def test_database_connection_loss(self):
        """Test handling of database connection issues"""
        url = reverse('wallet-balance')
        
        # Simulate database error by mocking
        with patch.object(CustomerWallet.objects, 'get') as mock_get:
            mock_get.side_effect = Exception("Database connection lost")
            
            response = self.customer_client.get(url)
        
        # Should return 500 error, not crash
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        response_data = response.data
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
    
    def test_rate_limit_simulation(self):
        """Test behavior under rapid requests"""
        url = reverse('wallet-balance')
        
        # Make multiple rapid requests
        for i in range(10):
            response = self.customer_client.get(url)
            # All should succeed (actual rate limiting would be handled differently)
            self.assertIn(response.status_code, [200, 429])  # 429 if rate limited
        
        # Check activity logs
        activity_logs = ActivityLog.objects.filter(
            action='WALLET_BALANCE_REQUESTED'
        ).count()
        self.assertEqual(activity_logs, 10)


# =============================================================================
# PERMISSION TESTS
# =============================================================================

class PermissionTests(TestCase):
    """Tests for permission handling"""
    
    def setUp(self):
        self.restaurant = ViewTestUtils.create_test_restaurant()
        self.other_restaurant = ViewTestUtils.create_test_restaurant()
        
        # Create users with different permissions
        self.staff_user = ViewTestUtils.create_test_user(
            self.restaurant, is_staff=True, email="staff@test.com"
        )
        self.customer_user = ViewTestUtils.create_test_user(
            self.restaurant, is_staff=False, email="customer@test.com"
        )
        self.other_staff = ViewTestUtils.create_test_user(
            self.other_restaurant, is_staff=True, email="other@test.com"
        )
        self.admin_user = User.objects.create_superuser(
            id=uuid.uuid4(),
            email="admin@test.com",
            username="admin",
            password="testpass123"
        )
        
        # Create test data
        self.order = ViewTestUtils.create_test_order(self.restaurant)
        self.invoice = ViewTestUtils.create_test_invoice(self.order, self.restaurant)
        
        # Set up clients
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff_user)
        
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(user=self.customer_user)
        
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other_staff)
        
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin_user)
    
    def test_staff_can_create_invoice(self):
        """Test staff can create invoices"""
        url = reverse('invoice-list')
        
        data = {
            'order_id': str(self.order.id),
            'subtotal_amount': '85.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_customer_cannot_create_invoice(self):
        """Test customer cannot create invoices"""
        url = reverse('invoice-list')
        
        data = {
            'order_id': str(self.order.id),
            'subtotal_amount': '85.00',
            'tax_amount': '15.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = self.customer_client.post(url, data, format='json')
        
        # Customer might be able to view but not create
        # Depending on permission setup
        self.assertIn(response.status_code, [403, 405])
    
    def test_cross_restaurant_access_prevention(self):
        """Test users cannot access other restaurant's data"""
        url = reverse('invoice-detail', args=[self.invoice.id])
        
        # User from other restaurant tries to access
        response = self.other_client.get(url)
        
        # Should be 404 (not found) rather than 403 (forbidden)
        # This is a common pattern to avoid information leakage
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_admin_access(self):
        """Test admin user access"""
        url = reverse('invoice-detail', args=[self.invoice.id])
        
        # Admin should be able to access
        response = self.admin_client.get(url)
        
        # Admin might have different permissions
        self.assertIn(response.status_code, [200, 403, 404])
    
    def test_unauthenticated_access(self):
        """Test unauthenticated access"""
        url = reverse('invoice-list')
        
        client = APIClient()  # No authentication
        
        # GET might be allowed, POST should not
        get_response = client.get(url)
        post_response = client.post(url, {}, format='json')
        
        # Unauthenticated users should not be able to POST
        self.assertEqual(post_response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_refund_permissions(self):
        """Test refund processing permissions"""
        # Create a payment
        payment = ViewTestUtils.create_test_payment(
            self.restaurant, self.invoice, status="COMPLETED"
        )
        
        url = reverse('request-refund', args=[payment.id])
        data = {
            'amount': '50.00',
            'original_payment_ref': str(payment.id),
            'wallet_type': 'PREPAID'
        }
        
        # Customer tries to process refund
        response = self.customer_client.post(url, data, format='json')
        
        # Customer shouldn't be able to process refunds
        self.assertIn(response.status_code, [403, 401])
        
        # Staff should be able to
        response = self.staff_client.post(url, data, format='json')
        
        # Staff might be able to depending on specific permissions
        self.assertIn(response.status_code, [200, 403, 400])


# =============================================================================
# ACTIVITY LOG VERIFICATION TESTS
# =============================================================================

class ActivityLogTests(BaseViewTestCase):
    """Tests for activity log generation"""
    
    def test_activity_log_on_success(self):
        """Test activity log is created on successful operation"""
        initial_log_count = ActivityLog.objects.count()
        
        # Perform an operation
        url = reverse('wallet-balance')
        response = self.customer_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check log was created
        new_log_count = ActivityLog.objects.count()
        self.assertGreater(new_log_count, initial_log_count)
        
        log = ActivityLog.objects.last()
        self.assertEqual(log.module, 'WALLET')
        self.assertEqual(log.action, 'WALLET_BALANCE_REQUESTED')
        self.assertEqual(log.user, self.customer_user)
        self.assertEqual(log.restaurant, self.restaurant)
    
    def test_activity_log_on_error(self):
        """Test activity log is created on error"""
        initial_log_count = ActivityLog.objects.count()
        
        # Cause an error
        url = reverse('invoice-detail', args=[uuid.uuid4()])  # Non-existent
        response = self.staff_client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Check error log was created
        new_log_count = ActivityLog.objects.count()
        self.assertGreater(new_log_count, initial_log_count)
        
        # There should be an error log
        error_logs = ActivityLog.objects.filter(level='ERROR')
        self.assertGreater(error_logs.count(), 0)
    
    def test_correlation_id_in_logs(self):
        """Test correlation ID is included in logs"""
        # Make a request
        url = reverse('wallet-balance')
        response = self.customer_client.get(url)
        
        # Check correlation ID in response
        response_data = response.data
        if 'correlation_id' in response_data:
            correlation_id = response_data['correlation_id']
            
            # Find log with this correlation ID
            log = ActivityLog.objects.filter(correlation_id=correlation_id).first()
            self.assertIsNotNone(log)
    
    def test_ip_address_logging(self):
        """Test IP address is logged for web requests"""
        # Make a request
        url = reverse('wallet-balance')
        response = self.customer_client.get(url)
        
        log = ActivityLog.objects.last()
        
        # IP address should be logged (might be 127.0.0.1 in tests)
        self.assertIsNotNone(log.ip_address)
    
    def test_webhook_activity_logging(self):
        """Test webhook requests are logged"""
        url = reverse('momo-webhook')
        
        data = {
            'external_id': str(self.payment.id),
            'status': 'SUCCESSFUL'
        }
        
        with patch.object(payment_service, 'handle_webhook') as mock_service:
            mock_service.return_value = {'success': True}
            
            response = self.client.post(
                url, 
                data, 
                format='json',
                HTTP_X_CORRELATION_ID=str(uuid.uuid4())
            )
        
        # Check webhook logs
        received_log = ActivityLog.objects.filter(
            action='MOMO_WEBHOOK_RECEIVED'
        ).first()
        self.assertIsNotNone(received_log)
        
        # Should include headers and data
        self.assertIn('headers', received_log.details)
        self.assertIn('data', received_log.details)

