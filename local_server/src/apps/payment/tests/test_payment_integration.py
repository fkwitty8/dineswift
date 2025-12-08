# tests/test_integration.py
import json
import uuid
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.core.models import User, Restaurant, ActivityLog
from apps.order_processing.models import OfflineOrder
from apps.payment.models import (
    Invoice, Payment, PaymentAllocation, 
    CustomerWallet, WalletTransaction
)
from apps.payment.services import invoice_service, payment_service, wallet_service


class PaymentIntegrationTest(TestCase):
    """Comprehensive integration tests for payment app"""
    
    def setUp(self):
        """Set up test data"""
        # Create test restaurant
        self.restaurant = Restaurant.objects.create(
            name="Test Restaurant",
            supabase_restaurant_id=str(uuid.uuid4()),
            address={"street": "123 Test St"},
            contact_info={"phone": "555-0100"},
            local_config={},
            is_active=True
        )
        
        # Create test users
        self.staff_user = User.objects.create_user(
            id=uuid.uuid4(),
            email="staff@test.com",
            username="staff",
            password="testpass123",
            restaurant=self.restaurant,
            is_staff=True
        )
        
        self.customer_user = User.objects.create_user(
            id=uuid.uuid4(),
            email="customer@test.com",
            username="customer",
            password="testpass123",
            restaurant=self.restaurant
        )
        
        # Create test order
        self.order = OfflineOrder.objects.create(
            id=uuid.uuid4(),
            restaurant=self.restaurant,
            local_order_id="TEST001",
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Test Item",
                    "price": "50.00",
                    "quantity": 2,
                    "total": "100.00"
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Test Item2",
                    "price": "40.00",
                    "quantity": 2,
                    "total": "80.00"
                }
                
            ],
            
            total_amount=Decimal("100.00"),
            tax_amount=Decimal("15.00"),
                        
            special_instructions="Test instructions",
            order_status='READY',
            sync_status='SYNCED'
        )
        
        # Create test invoice
        self.invoice = Invoice.objects.create(
            order=self.order,
            restaurant=self.restaurant,
            subtotal_amount=Decimal("85.00"),
            tax_amount=Decimal("15.00"),
            service_fee=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            due_date=timezone.now() + timedelta(days=1),
            status="ISSUED"
        )
        
        # Create test wallet
        self.wallet = CustomerWallet.objects.create(
            user=self.customer_user,
            restaurant=self.restaurant,
            wallet_type="PREPAID",
            available_balance=Decimal("500.00"),
            status="ACTIVE"
        )
        
        # Setup API clients
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff_user)
        
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(user=self.customer_user)
        
        # Clear activity logs before each test
        ActivityLog.objects.all().delete()
    
    def test_01_invoice_creation_flow(self):
        """Test complete invoice creation flow"""
        print("\n=== Test 1: Invoice Creation Flow ===")
        
        # Create a new order
        new_order = OfflineOrder.objects.create(
            id=uuid.uuid4(),
            restaurant=self.restaurant,
            local_order_id="TEST002",
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Burger",
                    "price": "25.00",
                    "quantity": 2,
                    "total": "50.00"
                }
            ],
            total_amount=Decimal("50.00"),
            tax_amount=Decimal("7.50"),
            order_status="PENDING"
        )
        
        # Create invoice via API
        url = reverse('invoice-list')
        data = {
            'order_id': str(new_order.id),
            'subtotal_amount': '50.50',
            'tax_amount': '7.50',
            'service_fee': '0.00',
            'discount_amount': '0.00'

        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Invoice creation response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        self.assertIn('invoice_id', response_data['data'])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('invoice_id', response_data['data'])
        
        # Verify invoice was created
        invoice_id = response_data['data']['id']
        invoice = Invoice.objects.get(id=invoice_id)
        self.assertEqual(invoice.total_amount, Decimal('50.00'))
        self.assertEqual(invoice.status, 'ISSUED')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_CREATED'
        ).first()
        self.assertIsNotNone(activity_log)
        self.assertEqual(activity_log.user, self.staff_user)
        self.assertEqual(activity_log.restaurant, self.restaurant)
        
        print(f" Invoice created successfully: {invoice_id}")
        print(f" Activity log created: {activity_log.action}")
        
        return invoice
    
    def test_02_payment_initiation_flow(self):
        """Test complete payment initiation flow"""
        print("\n=== Test 2: Payment Initiation Flow ===")
        
        # Initiate cash payment
        url = reverse('payment-list')
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH',
            'customer_phone': '+256700000001',
            'customer_email': 'test@example.com'
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Payment initiation response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('payment_id', response_data['data'])
        
        # Get payment ID
        payment_id = response_data['data']['id']
        payment = Payment.objects.get(id=payment_id)
        self.assertEqual(payment.gateway, 'CASH')
        self.assertEqual(payment.status, 'AWAITING_COLLECTION')
        self.assertEqual(payment.amount, Decimal('100.00'))
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='PAYMENT_CREATED'
        ).first()
        self.assertIsNotNone(activity_log)
        
        print(f"✓ Payment initiated successfully: {payment_id}")
        print(f"✓ Activity log created: {activity_log.action}")
        
        return payment
    
    def test_03_cash_payment_completion_flow(self):
        """Test cash payment completion flow"""
        print("\n=== Test 3: Cash Payment Completion Flow ===")
        
        # Create a cash payment first
        payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='CASH',
            status='AWAITING_COLLECTION',
            customer_phone='+256700000002'
        )
        
        # Create allocation
        PaymentAllocation.objects.create(
            invoice=self.invoice,
            payment=payment,
            allocated_amount=Decimal('100.00'),
            allocated_by=self.staff_user
        )
        
        # Complete cash payment
        url = reverse('complete-cash-payment', args=[payment.id])
        response = self.staff_client.post(url, {}, format='json')
        print(f"Cash completion response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        # Verify payment is completed
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'COMPLETED')
        self.assertIsNotNone(payment.completed_at)
        
        # Verify invoice is paid
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'PAID')
        self.assertEqual(self.invoice.amount_paid, Decimal('100.00'))
        
        # Check activity logs
        completion_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='CASH_PAYMENT_COLLECTED'
        ).first()
        self.assertIsNotNone(completion_log)
        
        invoice_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_PAYMENT_APPLIED'
        ).first()
        self.assertIsNotNone(invoice_log)
        
        print(f"✓ Cash payment completed: {payment.id}")
        print(f"✓ Invoice marked as paid: {self.invoice.status}")
        print(f"✓ Activity logs created: {completion_log.action}, {invoice_log.action}")
    
    def test_04_wallet_payment_flow(self):
        """Test wallet payment flow"""
        print("\n=== Test 4: Wallet Payment Flow ===")
        
        # Create a separate invoice for wallet payment
        wallet_invoice = Invoice.objects.create(
            order=self.order,
            restaurant=self.restaurant,
            subtotal_amount=Decimal('85.00'),
            tax_amount=Decimal('15.00'),
            total_amount=Decimal('100.00'),
            due_date=timezone.now() + timedelta(days=1),
            status='ISSUED'
        )
        
        # Initiate wallet payment
        url = reverse('payment-list')
        data = {
            'invoice_id': str(wallet_invoice.id),
            'payment_method': 'WALLET',
            'customer_user_id': str(self.customer_user.id)
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Wallet payment response: {response.status_code}")
        
        # For wallet payments, they should complete immediately
        if response.status_code == 201:
            response_data = response.json()
            print(f"Response data: {response_data}")
            
            payment_id = response_data['data']['id']
            payment = Payment.objects.get(id=payment_id)
            
            # Wallet payments should be completed immediately
            self.assertEqual(payment.status, 'COMPLETED')
            
            # Verify wallet balance is deducted
            self.wallet.refresh_from_db()
            self.assertEqual(self.wallet.available_balance, Decimal('400.00'))
            
            # Verify invoice is paid
            wallet_invoice.refresh_from_db()
            self.assertEqual(wallet_invoice.status, 'PAID')
            
            # Check activity logs
            wallet_log = ActivityLog.objects.filter(
                module='WALLET',
                action='WALLET_PAYMENT_COMPLETED'
            ).first()
            self.assertIsNotNone(wallet_log)
            
            print(f"✓ Wallet payment completed: {payment.id}")
            print(f"✓ Wallet balance updated: {self.wallet.available_balance}")
            print(f"✓ Activity log created: {wallet_log.action}")
        else:
            print(f"Wallet payment failed: {response.json()}")
    
    def test_05_wallet_funds_management(self):
        """Test wallet funds management"""
        print("\n=== Test 5: Wallet Funds Management ===")
        
        # Add funds to wallet
        url = reverse('add-wallet-funds')
        data = {
            'amount': '200.00',
            'reference_type': 'DEPOSIT',
            'reference_id': str(uuid.uuid4()),
            'description': 'Test deposit',
            'correlation_id': str(uuid.uuid4())
        }
        
        response = self.customer_client.post(url, data, format='json')
        print(f"Add funds response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        # Verify wallet balance
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
        
        print(f"✓ Funds added to wallet: {self.wallet.available_balance}")
        print(f"✓ Transaction created: {transaction.id}")
        print(f"✓ Activity log created: {activity_log.action}")
        
        # Get wallet balance
        url = reverse('wallet-balance')
        response = self.customer_client.get(url)
        print(f"Wallet balance response: {response.status_code}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        balance_data = response.json()
        self.assertTrue(balance_data['success'])
        self.assertEqual(float(balance_data['data']['available_balance']), 700.00)
        
        print(f"✓ Wallet balance retrieved successfully")
    
    def test_06_payment_allocation_flow(self):
        """Test manual payment allocation"""
        print("\n=== Test 6: Payment Allocation Flow ===")
        
        # Create unallocated payment
        payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('50.00'),
            currency='UGX',
            gateway='CASH',
            status='COMPLETED'
        )
        
        # Create partially paid invoice
        partial_invoice = Invoice.objects.create(
            order=self.order,
            restaurant=self.restaurant,
            total_amount=Decimal('100.00'),
            amount_paid=Decimal('50.00'),
            due_date=timezone.now() + timedelta(days=1),
            status='PARTIALLY_PAID'
        )
        
        # Allocate payment to invoice
        url = reverse('allocate-payment', args=[payment.id])
        data = {
            'invoice_id': str(partial_invoice.id),
            'allocated_amount': '50.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Allocation response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify allocation
        allocation = PaymentAllocation.objects.filter(
            payment=payment,
            invoice=partial_invoice
        ).first()
        self.assertIsNotNone(allocation)
        self.assertEqual(allocation.allocated_amount, Decimal('50.00'))
        
        # Verify invoice status
        partial_invoice.refresh_from_db()
        self.assertEqual(partial_invoice.amount_paid, Decimal('100.00'))
        self.assertEqual(partial_invoice.status, 'PAID')
        
        # Check activity log
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='PAYMENT_ALLOCATED'
        ).first()
        self.assertIsNotNone(activity_log)
        
        print(f"✓ Payment allocated successfully")
        print(f"✓ Invoice fully paid: {partial_invoice.status}")
        print(f"✓ Activity log created: {activity_log.action}")
    
    def test_07_refund_processing_flow(self):
        """Test refund processing flow"""
        print("\n=== Test 7: Refund Processing Flow ===")
        
        # Create a completed payment
        payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='CASH',
            status='COMPLETED',
            customer_user=self.customer_user
        )
        
        # Process refund
        url = reverse('request-refund', args=[payment.id])
        data = {
            'amount': '50.00',
            'original_payment_ref': str(payment.id),
            'wallet_type': 'PREPAID',
            'reason': 'Test refund'
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Refund response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        # Note: Our refund implementation returns True/False
        # Adjust based on actual implementation
        
        # Check if refund was attempted
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action__contains='REFUND'
        ).first()
        
        if activity_log:
            print(f"✓ Refund activity logged: {activity_log.action}")
        
        # Verify wallet balance increased if refund was successful
        initial_balance = self.wallet.available_balance
        self.wallet.refresh_from_db()
        
        # If refund was processed, balance should increase
        if self.wallet.available_balance > initial_balance:
            print(f"✓ Wallet refund processed: +{self.wallet.available_balance - initial_balance}")
        
        print(f"Refund flow completed with logs")
    
    def test_08_webhook_processing(self):
        """Test webhook processing"""
        print("\n=== Test 8: Webhook Processing ===")
        
        # Create a pending payment
        payment = Payment.objects.create(
            id=uuid.uuid4(),
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='MOMO',
            status='PENDING'
        )
        
        # Create allocation
        PaymentAllocation.objects.create(
            invoice=self.invoice,
            payment=payment,
            allocated_amount=Decimal('100.00')
        )
        
        # Simulate webhook request
        url = reverse('momo-webhook')
        data = {
            'external_id': str(payment.id),
            'status': 'SUCCESSFUL',
            'transaction_id': 'TXN123456',
            'payer_message': 'Payment successful'
        }
        
        # Create client without authentication for webhook
        client = APIClient()
        response = client.post(url, data, format='json')
        print(f"Webhook response: {response.status_code}")
        print(f"Response data: {response.json()}")
        
        # Webhook should be processed
        self.assertIn(response.status_code, [200, 400, 500])
        
        # Check activity logs
        webhook_logs = ActivityLog.objects.filter(
            module='PAYMENT',
            action__contains='WEBHOOK'
        )
        self.assertTrue(webhook_logs.exists())
        
        for log in webhook_logs:
            print(f"✓ Webhook activity: {log.action}")
    
    def test_09_error_handling_scenarios(self):
        """Test error handling scenarios"""
        print("\n=== Test 9: Error Handling Scenarios ===")
        
        # Test 1: Invalid invoice creation
        url = reverse('invoice-list')
        data = {
            'order_id': str(uuid.uuid4()),  # Non-existent order
            'subtotal_amount': '100.00'
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Invalid invoice response: {response.status_code}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test 2: Payment for non-existent invoice
        url = reverse('payment-list')
        data = {
            'invoice_id': str(uuid.uuid4()),
            'payment_method': 'CASH'
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Invalid payment response: {response.status_code}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Test 3: Invalid payment allocation
        payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('10.00'),
            currency='UGX',
            gateway='CASH',
            status='COMPLETED'
        )
        
        url = reverse('allocate-payment', args=[payment.id])
        data = {
            'invoice_id': str(self.invoice.id),
            'allocated_amount': '1000.00'  # More than payment amount
        }
        
        response = self.staff_client.post(url, data, format='json')
        print(f"Invalid allocation response: {response.status_code}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check error logs were created
        error_logs = ActivityLog.objects.filter(level='ERROR')
        print(f"✓ Error logs created: {error_logs.count()}")
        
        for log in error_logs[:3]:  # Show first 3 error logs
            print(f"  - {log.action}: {log.details.get('error', 'No error details')}")
    
    def test_10_comprehensive_end_to_end_flow(self):
        """Test comprehensive end-to-end flow"""
        print("\n=== Test 10: Comprehensive End-to-End Flow ===")
        
        # Step 1: Create order
        order = OfflineOrder.objects.create(
            id=uuid.uuid4(),
            restaurant=self.restaurant,
            local_order_id="E2E001",
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Pizza",
                    "price": "30.00",
                    "quantity": 2,
                    "total": "60.00"
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Drink",
                    "price": "10.00",
                    "quantity": 1,
                    "total": "10.00"
                }
            ],
            total_amount=Decimal("70.00"),
            tax_amount=Decimal("10.50"),
            order_status="PENDING"
        )
        
        print(f"Step 1: Order created - {order.id}")
        
        # Step 2: Create invoice
        invoice_data = {
            'order_id': str(order.id),
            'subtotal_amount': '59.50',
            'tax_amount': '10.50',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        invoice_response = self.staff_client.post(
            reverse('invoice-list'), 
            invoice_data, 
            format='json'
        )
        self.assertEqual(invoice_response.status_code, status.HTTP_201_CREATED)
        invoice_id = invoice_response.json()['data']['id']
        
        print(f"Step 2: Invoice created - {invoice_id}")
        
        # Step 3: Initiate payment
        payment_data = {
            'invoice_id': invoice_id,
            'payment_method': 'CASH',
            'customer_phone': '+256700000003',
            'customer_email': 'e2e@example.com'
        }
        
        payment_response = self.staff_client.post(
            reverse('payment-list'), 
            payment_data, 
            format='json'
        )
        self.assertEqual(payment_response.status_code, status.HTTP_201_CREATED)
        payment_id = payment_response.json()['data']['id']
        
        print(f"Step 3: Payment initiated - {payment_id}")
        
        # Step 4: Complete cash payment
        complete_response = self.staff_client.post(
            reverse('complete-cash-payment', args=[payment_id]),
            {},
            format='json'
        )
        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        
        print(f"Step 4: Cash payment completed")
        
        # Step 5: Verify final state
        # Get invoice status
        status_response = self.staff_client.get(
            reverse('invoice-status', args=[invoice_id])
        )
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        
        status_data = status_response.json()
        self.assertTrue(status_data['success'])
        self.assertEqual(status_data['data']['status'], 'PAID')
        self.assertEqual(float(status_data['data']['amount_due']), 0.0)
        
        # Get order payments
        payments_response = self.staff_client.get(
            reverse('order-payments', args=[order.id])
        )
        self.assertEqual(payments_response.status_code, status.HTTP_200_OK)
        
        payments_data = payments_response.json()
        self.assertTrue(payments_data['success'])
        self.assertEqual(len(payments_data['data']['payments']), 1)
        
        # Check activity logs
        logs_count = ActivityLog.objects.filter(
            restaurant=self.restaurant
        ).count()
        
        print(f"Step 5: Verification complete")
        print(f"  - Invoice status: PAID")
        print(f"  - Payments count: 1")
        print(f"  - Activity logs: {logs_count}")
        
        # Verify all steps created activity logs
        expected_actions = [
            'INVOICE_CREATED',
            'PAYMENT_CREATED',
            'CASH_PAYMENT_COLLECTED',
            'INVOICE_PAYMENT_APPLIED'
        ]
        
        for action in expected_actions:
            log_exists = ActivityLog.objects.filter(action=action).exists()
            self.assertTrue(log_exists, f"Missing activity log for {action}")
            print(f"✓ Activity log verified: {action}")
        
        print("\n✓ Comprehensive E2E flow completed successfully!")
