import pytest
from decimal import Decimal
from cloud_api.models import User, Restaurant, Order, Payment


@pytest.mark.django_db
class TestPaymentProcessing:
    
    @pytest.fixture
    def setup_data(self):
        user = User.objects.create_user(
            username='customer',
            email='customer@test.com',
            phone_number='+1234567890'
        )
        
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        
        order = Order.objects.create(
            restaurant=restaurant,
            order_type='sales',
            status='pending',
            total_amount=Decimal('25.99')
        )
        
        return {'user': user, 'restaurant': restaurant, 'order': order}
    
    def test_create_payment(self, setup_data):
        """Test payment creation"""
        payment = Payment.objects.create(
            idempotency_key='test-payment-123',
            payment_type='order',
            reference_id=setup_data['order'].id,
            amount=Decimal('25.99'),
            phone_number='+1234567890'
        )
        
        assert payment.amount == Decimal('25.99')
        assert payment.status == 'pending'
        assert payment.payment_method == 'momo'
    
    def test_payment_completion(self, setup_data):
        """Test payment status update"""
        payment = Payment.objects.create(
            idempotency_key='test-payment-456',
            payment_type='order',
            reference_id=setup_data['order'].id,
            amount=Decimal('25.99'),
            phone_number='+1234567890',
            status='completed',
            momo_transaction_id='MOMO123456'
        )
        
        assert payment.status == 'completed'
        assert payment.momo_transaction_id == 'MOMO123456'