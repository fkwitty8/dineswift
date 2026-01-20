import pytest
import uuid
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.core.models import Restaurant, User, SyncQueue
from apps.order_processing.models import OfflineOrder


@pytest.fixture
def restaurant():
    """Create a test restaurant"""
    return Restaurant.objects.create(
        supabase_restaurant_id=uuid.uuid4(),
        name='Test Restaurant',
        address={'city': 'Test City'},
        contact_info={'email': 'test@restaurant.com'},
        local_config={'timezone': 'UTC'},
        is_active=True
    )


@pytest.fixture
def test_user(restaurant):
    """Create a test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123',
        restaurant=restaurant
    )


@pytest.fixture
def admin_user(restaurant):
    """Create an admin user"""
    user = User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpass123'
    )
    user.restaurant = restaurant
    user.save()
    return user


@pytest.fixture
def authenticated_client(test_user):
    """Create an authenticated API client"""
    client = APIClient()
    client.force_authenticate(user=test_user)
    return client


@pytest.fixture
def admin_client(admin_user):
    """Create an authenticated admin API client"""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def offline_order(restaurant):
    """Create a test offline order"""
    return OfflineOrder.objects.create(
        restaurant=restaurant,
        local_order_id=f'LOCAL-{uuid.uuid4().hex[:8]}',
        order_items=[{'item_id': '1', 'name': 'Test Item', 'price': 10.0, 'quantity': 2}],
        total_amount=20.0,
        tax_amount=2.0,
        order_status='PENDING',
        sync_status='PENDING'
    )


@pytest.fixture
def sync_queue_item(restaurant):
    """Create a test sync queue item"""
    return SyncQueue.objects.create(
        restaurant=restaurant,
        sync_type='ORDER_CREATE',
        status='PENDING',
        payload={'local_order_id': 'test-123'},
        priority=5,
        max_retries=3
    )


@pytest.fixture
def failed_sync_item(restaurant):
    """Create a failed sync queue item"""
    return SyncQueue.objects.create(
        restaurant=restaurant,
        sync_type='ORDER_CREATE',
        status='FAILED',
        payload={'local_order_id': 'test-failed-123'},
        retry_count=2,
        max_retries=5,
        next_retry=timezone.now() - timedelta(minutes=5)  # Ready for retry
    )


@pytest.fixture
def conflict_sync_item(restaurant):
    """Create a sync queue item with conflict"""
    return SyncQueue.objects.create(
        restaurant=restaurant,
        sync_type='ORDER_CREATE',
        status='CONFLICT',
        payload={'local_order_id': 'test-conflict-123'},
        conflict_data={
            'local_version': {'updated_at': '2024-01-01T10:00:00Z', 'data': {'status': 'PENDING'}},
            'remote_version': {'updated_at': '2024-01-01T11:00:00Z', 'data': {'status': 'COMPLETED'}}
        }
    )


@pytest.fixture
def completed_sync_item(restaurant):
    """Create a completed sync queue item"""
    return SyncQueue.objects.create(
        restaurant=restaurant,
        sync_type='ORDER_CREATE',
        status='COMPLETED',
        payload={'local_order_id': 'test-completed-123'},
        supabase_id='supabase-123',
        retry_count=0
    )


@pytest.fixture
def mock_request():
    """Create a mock request object"""
    class MockRequest:
        def __init__(self):
            self.user = Mock()
            self.user.restaurant_id = uuid.uuid4()
            self.META = {}
    
    return MockRequest()