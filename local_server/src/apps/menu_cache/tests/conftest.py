import pytest
import uuid
from django.core.cache import cache
from apps.menu_cache.models import MenuCache
from apps.core.models import Restaurant, User
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

# Disable Redis and caching for tests to avoid connection issues
settings.CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# In conftest.py, update the cache settings:
# In conftest.py, update the cache settings:
settings.CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# # Disable Redis for Channels
# settings.CHANNEL_LAYERS = {
#     'default': {
#         'BACKEND': 'channels.layers.InMemoryChannelLayer',  # Use in-memory layer for tests
#     },
# }

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
def sample_menu_data():
    """Sample menu data for testing"""
    return {
        "categories": [
            {
                "id": str(uuid.uuid4()),
                "name": "Appetizers",
                "description": "Start your meal right",
                "items": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Garlic Bread",
                        "description": "Fresh baked bread with garlic butter",
                        "price": "5.99",
                        "category": "Appetizers",
                        "is_available": True,
                        "preparation_time": 10,
                        "ingredients": ["bread", "garlic", "butter", "parsley"],
                        "allergens": ["gluten", "dairy"],
                        "image_url": "https://example.com/garlic-bread.jpg"
                    }
                ]
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Main Courses",
                "description": "Hearty main dishes",
                "items": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Margherita Pizza",
                        "description": "Classic pizza with tomato and mozzarella",
                        "price": "12.99",
                        "category": "Main Courses",
                        "is_available": True,
                        "preparation_time": 20,
                        "ingredients": ["pizza dough", "tomato sauce", "mozzarella", "basil"],
                        "allergens": ["gluten", "dairy"],
                        "image_url": "https://example.com/pizza.jpg"
                    }
                ]
            }
        ]
    }

@pytest.fixture
def menu_cache(test_restaurant, sample_menu_data):
    """Create a menu cache instance"""
    return MenuCache.objects.create(
        restaurant=test_restaurant,
        menu_data=sample_menu_data,
        version=1,
        is_active=True
    )

@pytest.fixture
def inactive_menu_cache(test_restaurant, sample_menu_data):
    """Create an inactive menu cache instance"""
    return MenuCache.objects.create(
        restaurant=test_restaurant,
        menu_data=sample_menu_data,
        version=2,
        is_active=False
    )

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
async def async_test_restaurant(db):
    """Async version of test_restaurant fixture"""
    restaurant = await sync_to_async(Restaurant.objects.create)(
        supabase_restaurant_id=str(uuid.uuid4()),
        name='Test Restaurant',
        address={'street': '123 Test St'},
        contact_info={'phone': '555-0100'},
        is_active=True
    )
    return restaurant

@pytest.fixture
async def async_menu_cache(async_test_restaurant, sample_menu_data):
    """Async version of menu_cache fixture"""
    menu_cache = await sync_to_async(MenuCache.objects.create)(
        restaurant=async_test_restaurant,
        menu_data=sample_menu_data,
        version=1,
        is_active=True
    )
    return menu_cache

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test"""
    cache.clear()
    yield
    cache.clear()
    
@pytest.fixture
def test_user(db, test_restaurant):
    """Create a test user with restaurant association"""
    User = get_user_model()
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123',
        restaurant=test_restaurant
    )

@pytest.fixture
def authenticated_client(test_user):
    """Create an authenticated API client"""
    client = APIClient()
    client.force_authenticate(user=test_user)
    return client

@pytest.fixture
def api_client():
    """Create an unauthenticated API client"""
    return APIClient()
