import pytest
from django.conf import settings
from rest_framework.test import APIClient
from apps.core.models import Restaurant
from django.contrib.auth import get_user_model
from faker import Faker
import uuid

User = get_user_model()

# Disable Redis and caching for tests to avoid connection issues
settings.CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Disable Redis for Channels
settings.CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',  # Use in-memory layer for tests
    },
}

# Disable throttling for tests
settings.REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {},
}

@pytest.fixture(scope='session')
def django_db_setup():
    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'dineswift_local_test',
            'USER': 'postgres',
            'PASSWORD': 'root',
            'HOST': 'localhost',
            'PORT': '5432',
            'AUTOCOMMIT': True,  
            'ATOMIC_REQUESTS': True,
            'TIME_ZONE': 'UTC',
            'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False,
            'OPTIONS': {},
            'TEST': {
                'NAME': 'dineswift_local_test',
            }
        }
    }
  

@pytest.fixture
def api_client():
    return APIClient()

# --- BEGIN FIXTURE MODIFICATION ---

@pytest.fixture
def faker():
    """Provides a consistent Faker instance for generating unique data."""
    return Faker()

@pytest.fixture
def test_restaurant(db):
    return Restaurant.objects.create(
        supabase_restaurant_id=str(uuid.uuid4()),  # Always unique
        name='Test Restaurant',
        address={'street': '123 Test St'},
        contact_info={'phone': '555-0100'},
        is_active=True
    )

@pytest.fixture
def test_user(db, test_restaurant):
    """Create a test user with restaurant"""
    return User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com',
        restaurant=test_restaurant
    )

@pytest.fixture
def authenticated_client(api_client, test_user):
    """Use the test_user fixture instead of creating another user"""
    api_client.force_authenticate(user=test_user)
    return api_client

@pytest.fixture
def test_order(db, test_restaurant):
    """Create a test order"""
    from apps.order_processing.models import OfflineOrder
    from decimal import Decimal
    
    return OfflineOrder.objects.create(
        restaurant=test_restaurant,
        local_order_id='TEST-001',
        order_items=[
            {
                'id': '1',
                'name': 'Test Item',
                'price': '10.00',
                'quantity': 2
            }
        ],
        total_amount=Decimal('21.60'),
        tax_amount=Decimal('1.60'),
        order_status='PENDING'
    )