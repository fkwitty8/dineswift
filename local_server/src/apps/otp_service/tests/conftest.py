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
        {
  "table_number": null,
  "menu": {
    "categories": [
      {
        "name": "Buckets & Meals",
        "items": [
          {
            "id": "11111111-2222-3333-4444-555555555555",
            "name": "9 Pcs Original Recipe Bucket",
            "price": "34.99",
            "image_url": "https://placehold.co/400x250/C8102E/FFFFFF?text=Original+Bucket",
            "description": "9 pieces of Original Recipe chicken.",
            "is_available": true,
            "display_order": 1,
            "kitchen_station": "Fry Station",
            "preparation_time": 20
          },
          {
            "id": "22222222-3333-4444-5555-666666666666",
            "name": "Zinger Burger Meal",
            "price": "12.50",
            "image_url": "https://placehold.co/400x250/C8102E/FFFFFF?text=Zinger+Meal",
            "description": "Spicy Zinger fillet, lettuce, and mayo.",
            "is_available": true,
            "display_order": 2,
            "kitchen_station": "Assembly",
            "preparation_time": 8
          }
        ],
        "description": "The Colonels Original Recipe and Zinger options."
      },
      {
        "name": "Sides & Desserts",
        "items": [
          {
            "id": "33333333-4444-5555-6666-777777777777",
            "name": "Large Fries",
            "price": "4.99",
            "image_url": "https://placehold.co/400x250/C8102E/FFFFFF?text=KFC+Fries",
            "description": "Our signature salted fries.",
            "is_available": true,
            "display_order": 1,
            "kitchen_station": "Fry Station",
            "preparation_time": 5
          },
          {
            "id": "44444444-5555-6666-7777-888888888888",
            "name": "Coleslaw",
            "price": "3.50",
            "image_url": "https://placehold.co/400x250/C8102E/FFFFFF?text=Coleslaw",
            "description": "Classic creamy coleslaw.",
            "is_available": true,
            "display_order": 2,
            "kitchen_station": "Cold Prep",
            "preparation_time": 2
          }
        ],
        "description": "Fries, Gravy, and famous Coleslaw."
      }
    ],
    "last_synced": "2025-11-18T10:00:00Z",
    "restaurant_name": "KFC - Test Location"
  },
  "cached": true
}
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