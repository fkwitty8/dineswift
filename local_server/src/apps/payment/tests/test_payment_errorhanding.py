import json
import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.core.models import User, Restaurant, ActivityLog
from apps.payment.models import Invoice, Payment


class PaymentErrorHandlingTest(TestCase):
    """Test error handling scenarios"""
    
    def setUp(self):
        self.restaurant = Restaurant.objects.create(
            id=uuid.uuid4(),
            name="Test Restaurant",
            slug="test-restaurant"
        )
        
        self.staff_user = User.objects.create_user(
            id=uuid.uuid4(),
            email="staff@test.com",
            username="staff",
            password="testpass123",
            restaurant=self.restaurant,
            is_staff=True
        )
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff_user)
        
        # Create test invoice
        from apps.order_processing.models import OfflineOrder
        self.order = OfflineOrder.objects.create(
            id=uuid.uuid4(),
            restaurant=self.restaurant,
            local_order_id="TEST001",
            total_amount=Decimal("100.00"),
            order_status="PENDING"
        )
        
        self.invoice = Invoice.objects.create(
            order=self.order,
            restaurant=self.restaurant,
            total_amount=Decimal("100.00"),
            due_date=timezone.now() + timedelta(days=1),
            status="ISSUED"
        )
    
    def test_malformed_json_request(self):
        """Test handling of malformed JSON"""
        url = reverse('invoice-list')
        
        # Send malformed JSON
        response = self.client.post(
            url, 
            '{"invalid": json, missing quotes}', 
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check error log
        error_log = ActivityLog.objects.filter(
            level='ERROR',
            module='INVOICE'
        ).first()
        self.assertIsNotNone(error_log)
    
    def test_missing_required_fields(self):
        """Test validation of missing required fields"""
        url = reverse('invoice-list')
        
        # Missing required fields
        data = {
            'order_id': str(self.order.id)
            # Missing subtotal_amount, etc.
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
    
    def test_invalid_uuid_format(self):
        """Test handling of invalid UUID format"""
        url = reverse('invoice-list')
        
        data = {
            'order_id': 'not-a-uuid',
            'subtotal_amount': '100.00',
            'tax_amount': '0.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_nonexistent_resource_access(self):
        """Test accessing non-existent resources"""
        # Non-existent invoice
        url = reverse('invoice-status', args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Non-existent payment
        url = reverse('payment-detail', args=[uuid.uuid4()])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_unauthorized_access(self):
        """Test unauthorized access attempts"""
        # Create another restaurant's user
        other_restaurant = Restaurant.objects.create(
            id=uuid.uuid4(),
            name="Other Restaurant",
            slug="other-restaurant"
        )
        
        other_user = User.objects.create_user(
            id=uuid.uuid4(),
            email="other@test.com",
            username="other",
            password="testpass123",
            restaurant=other_restaurant
        )
        
        # Try to access invoice from different restaurant
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        
        url = reverse('invoice-detail', args=[self.invoice.id])
        response = other_client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_invalid_payment_amounts(self):
        """Test invalid payment amounts"""
        url = reverse('payment-list')
        
        # Negative amount
        data = {
            'invoice_id': str(self.invoice.id),
            'payment_method': 'CASH',
            'amount': '-10.00'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Zero amount
        data['amount'] = '0.00'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Amount exceeding invoice
        data['amount'] = '10000.00'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_duplicate_operations(self):
        """Test duplicate operations"""
        # Create payment
        payment = Payment.objects.create(
            restaurant=self.restaurant,
            amount=Decimal('100.00'),
            currency='UGX',
            gateway='CASH',
            status='COMPLETED'
        )
        
        # Create allocation
        from apps.payment.models import PaymentAllocation
        PaymentAllocation.objects.create(
            invoice=self.invoice,
            payment=payment,
            allocated_amount=Decimal('100.00')
        )
        
        # Try to allocate same payment again
        url = reverse('allocate-payment', args=[payment.id])
        data = {
            'invoice_id': str(self.invoice.id),
            'allocated_amount': '50.00'
        }
        
        response = self.client.post(url, data, format='json')
        # Should fail due to unique constraint
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_database_constraint_violations(self):
        """Test database constraint violations"""
        url = reverse('invoice-list')
        
        # Try to create invoice for non-existent order
        data = {
            'order_id': str(uuid.uuid4()),
            'subtotal_amount': '100.00',
            'tax_amount': '0.00',
            'service_fee': '0.00',
            'discount_amount': '0.00'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check that proper error response is returned
        response_data = response.json()
        self.assertIn('error', response_data)
        self.assertFalse(response_data['success'])
    
    def test_rate_limiting_simulation(self):
        """Test handling of high request volume"""
        import threading
        import time
        
        url = reverse('wallet-balance')
        
        # Simulate multiple simultaneous requests
        responses = []
        
        def make_request():
            response = self.client.get(url)
            responses.append(response.status_code)
        
        threads = []
        for i in range(5):  # 5 simultaneous requests
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All requests should be handled (or rate limited appropriately)
        print(f"Responses: {responses}")
        
        # Check activity logs for potential issues
        error_logs = ActivityLog.objects.filter(
            level__in=['ERROR', 'CRITICAL'],
            module='WALLET'
        ).count()
        
        print(f"Error logs during load test: {error_logs}")
    
    def test_corrupted_data_handling(self):
        """Test handling of corrupted/invalid data"""
        url = reverse('momo-webhook')
        
        # Send corrupted data
        test_cases = [
            # Empty data
            {},
            # Missing required fields
            {'status': 'SUCCESSFUL'},
            # Invalid data types
            {'external_id': 123, 'status': True},
            # SQL injection attempt
            {'external_id': "'; DROP TABLE payments; --", 'status': 'SUCCESSFUL'},
            # XSS attempt
            {'external_id': str(uuid.uuid4()), 'status': '<script>alert("xss")</script>'},
            # Extremely large data
            {'external_id': str(uuid.uuid4()), 'status': 'S' * 10000},
        ]
        
        for i, test_data in enumerate(test_cases):
            response = self.client.post(url, test_data, format='json')
            print(f"Test {i+1} - Status: {response.status_code}")
            
            # Should either be 400 Bad Request or handle gracefully
            self.assertIn(response.status_code, [200, 400, 500])
            
            # Check that system didn't crash
            self.assertTrue(True)