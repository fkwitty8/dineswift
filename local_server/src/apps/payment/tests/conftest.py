import pytest
from decimal import Decimal
import uuid
import pytest
from django.utils import timezone
from datetime import timedelta
from apps.payment.models import Invoice, Payment, PaymentAllocation, CustomerWallet


    
@pytest.fixture
def test_order(test_restaurant):
    """Create a test order with all required fields"""
    from apps.order_processing.models import OfflineOrder
    
    order = OfflineOrder.objects.create(
        restaurant=test_restaurant,
        local_order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        order_items=[
            {
                "id": str(uuid.uuid4()),
                "name": "Test Item",
                "price": "10.99",
                "quantity": 2,
                "total": "21.98"
            }
        ],
        total_amount=Decimal('21.98'),
        tax_amount=Decimal('1.76'),

        special_instructions="Test instructions",
        order_status='READY',
        sync_status='SYNCED'
    )
    return order

@pytest.fixture
def test_second_order(test_restaurant):
    """Create a test order with all required fields"""
    from apps.order_processing.models import OfflineOrder
    
    order = OfflineOrder.objects.create(
        restaurant=test_restaurant,
        local_order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        order_items=[
            {
                "id": str(uuid.uuid4()),
                "name": "Test Item",
                "price": "10.99",
                "quantity": 2,
                "total": "21.98"
            }
        ],
        total_amount=Decimal('21.98'),
        tax_amount=Decimal('1.76'),

        special_instructions="Test instructions",
        order_status='READY',
        sync_status='SYNCED'
    )
    return order


@pytest.fixture
def test_restaurant():
    """Create a test restaurant"""
    from apps.core.models import Restaurant
    
    restaurant = Restaurant.objects.create(
        name="Test Restaurant",
        supabase_restaurant_id=str(uuid.uuid4()),
        address={"street": "123 Test St"},
        contact_info={"phone": "555-0100"},
        local_config={},
        is_active=True
    )
    return restaurant

@pytest.fixture
def invoice_instance(test_order, test_restaurant):
    """Create an invoice instance for testing"""
    return Invoice.objects.create(
        order=test_order,
        restaurant=test_restaurant,
        subtotal_amount=Decimal('100.00'),
        tax_amount=Decimal('18.00'),
        service_fee=Decimal('5.00'),
        discount_amount=Decimal('10.00'),
        total_amount=Decimal('113.00'),
        due_date=timezone.now() + timedelta(days=1),
        status='DRAFT'
    )

@pytest.fixture
def invoice_second_instance(test_second_order, test_restaurant):
    """Create an invoice instance for testing"""
    return Invoice.objects.create(
        order=test_second_order,
        restaurant=test_restaurant,
        subtotal_amount=Decimal('100.00'),
        tax_amount=Decimal('18.00'),
        service_fee=Decimal('5.00'),
        discount_amount=Decimal('10.00'),
        total_amount=Decimal('113.00'),
        due_date=timezone.now() + timedelta(days=1),
        status='DRAFT'
    )


@pytest.fixture
def payment_instance(test_restaurant, test_user):
    """Create a payment instance for testing"""
    return Payment.objects.create(
        restaurant=test_restaurant,
        amount=Decimal('113.00'),
        currency='UGX',
        gateway='MOMO',
        customer_phone='256712345678',
        customer_email='test@example.com',
        customer_user=test_user
    )

@pytest.fixture
def second_payment_instance(test_restaurant, test_user):
    """Create a payment instance for testing"""
    return Payment.objects.create(
        restaurant=test_restaurant,
        amount=Decimal('50.00'),
        currency='UGX',
        gateway='MOMO',
        customer_phone='256712345678',
        customer_email='test@example.com',
        customer_user=test_user
    )


@pytest.fixture
def completed_payment(test_restaurant, test_user):
    """Create a completed payment instance"""
    payment = Payment.objects.create(
        restaurant=test_restaurant,
        amount=Decimal('150.00'),
        currency='UGX',
        gateway='VISA',
        customer_user=test_user,
        status='COMPLETED',
        gateway_reference='REF123456'
    )
    payment.completed_at = timezone.now()
    payment.save()
    return payment

@pytest.fixture
def failed_payment(test_restaurant, test_user):
    """Create a failed payment instance"""
    return Payment.objects.create(
        restaurant=test_restaurant,
        amount=Decimal('75.00'),
        currency='UGX',
        gateway='MOMO',
        customer_user=test_user,
        status='FAILED',
        error_message='Insufficient funds',
        retry_count=2
    )

@pytest.fixture
def test_user(test_restaurant): # Required for thread-safe concurrent testing
    """Create a test user instance (used for concurrent testing)"""
    from django.contrib.auth import get_user_model
    User = get_user_model() 
    user = User.objects.create_user(
        username='testuser_concurrent',
        password='testpass123',
        restaurant_id=test_restaurant.id
    )
    return user


@pytest.fixture
def customer_wallet(test_user, test_restaurant):
    """Create a customer wallet for testing"""
    return CustomerWallet.objects.create(
        user_id=test_user.id,
        restaurant_id=test_restaurant.id,
        available_balance=Decimal('1000.00'),
        pending_balance=Decimal('0.00'),
        wallet_type='PREPAID',
        status='ACTIVE',
        currency='UGX'
    )

@pytest.fixture
def payment_allocation(payment_instance, invoice_instance, test_user):
    """Create a payment allocation for testing"""
    return PaymentAllocation.objects.create(
        invoice=invoice_instance,
        payment=payment_instance,
        allocated_amount=Decimal('50.00'),
        allocated_by=test_user
    )

@pytest.fixture
def authenticated_client(test_restaurant):
    """Create an authenticated API client"""
    from rest_framework.test import APIClient
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    user = User.objects.create_user(
        username='testuser',
        password='testpass123',
        restaurant_id=test_restaurant.id
    )
    
    client = APIClient()
    client.force_authenticate(user=user)
    return client

@pytest.fixture
def test_user_2(test_restaurant): # Required for thread-safe concurrent testing
    """Create a test user instance (used for concurrent testing)"""
    from django.contrib.auth import get_user_model
    User = get_user_model() 
    user = User.objects.create_user(
        username='testuser_concurrent_2',
        password='testpass123',
        restaurant_id=test_restaurant.id
    )
    return user
