import pytest
import uuid
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

import os
from django.conf import settings

@pytest.fixture(scope='session', autouse=True)
def ensure_static_root_exists():
    """
    Ensures that the STATIC_ROOT directory exists before running tests 
    to prevent UserWarnings from staticfiles finders.
    """
    static_root = settings.STATIC_ROOT
    if not os.path.exists(static_root):
        os.makedirs(static_root, exist_ok=True)

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
def otp_instance(test_order):
    """Create a test OTP instance"""
    from apps.otp_service.models import OTP
    
    otp = OTP.objects.create(
        order_id=test_order.id,
        otp_code='123456',
        expires_at=timezone.now() + timedelta(minutes=15),
        status='ACTIVE'
    )
    return otp

@pytest.fixture
def mock_request():
    """Mock request object for serializer context"""
    class MockUser:
        restaurant_id = 'test-restaurant-id'
    
    class MockRequest:
        user = MockUser()
    
    return MockRequest()

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
def expired_otp(test_order):
    """Create an expired OTP instance"""
    from apps.otp_service.models import OTP
    
    otp = OTP.objects.create(
        order_id=test_order.id,
        otp_code='999999',
        expires_at=timezone.now() - timedelta(minutes=30),
        status='ACTIVE'
    )
    return otp

@pytest.fixture
def revoked_otp(test_order):
    """Create a revoked OTP instance"""
    from apps.otp_service.models import OTP
    
    otp = OTP.objects.create(
        order_id=test_order.id,
        otp_code='888888',
        expires_at=timezone.now() + timedelta(minutes=15),
        status='REVOKED',
    
    )
    return otp

@pytest.fixture
def used_otp(test_order):
    """Create a used OTP instance"""
    from apps.otp_service.models import OTP
    
    otp = OTP.objects.create(
        order_id=test_order.id,
        otp_code='777777',
        expires_at=timezone.now() + timedelta(minutes=15),
        status='USED',
        verified_at=timezone.now()
    )
    return otp