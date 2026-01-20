import pytest
import uuid
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock

from apps.core.models import SyncQueue, ActivityLog, Restaurant


@pytest.mark.django_db
class TestSyncQueueModel:
    """Unit tests for SyncQueue model"""
    
    def test_sync_queue_creation(self, restaurant):
        """Test creating a SyncQueue item"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            priority=1,
            payload={'local_order_id': 'test-123'},
            max_retries=3,
        )
        
        assert sync_item.restaurant == restaurant
        assert sync_item.sync_type == 'ORDER_CREATE'
        assert sync_item.status == 'PENDING'
        assert sync_item.priority == 1
        assert sync_item.retry_count == 0
        assert sync_item.max_retries == 3
        assert sync_item.can_retry() == False  # Not failed yet
    
    def test_sync_queue_string_representation(self, restaurant):
        """Test string representation of SyncQueue"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'test': 'data'}
        )
        
        expected_str = f"ORDER_CREATE - PENDING"
        assert str(sync_item) == expected_str
    
    def test_can_retry_failed_item(self, restaurant):
        """Test can_retry for failed item with retries remaining"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            retry_count=2,
            max_retries=5
        )
        
        assert sync_item.can_retry() == True
    
    def test_cannot_retry_max_retries_reached(self, restaurant):
        """Test can_retry when max retries reached"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            retry_count=5,
            max_retries=5
        )
        
        assert sync_item.can_retry() == False
    
    def test_mark_retry_success(self, restaurant):
        """Test mark_retry for item with retries remaining"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            retry_count=2,
            max_retries=5
        )
        
        with patch('apps.core.models.timezone.now') as mock_now:
            fixed_time = timezone.make_aware(timezone.datetime(2024, 1, 1, 12, 0, 0))
            mock_now.return_value = fixed_time
            
            sync_item.mark_retry('Test error')
            
            assert sync_item.retry_count == 3
            assert sync_item.last_retry == fixed_time
            # Exponential backoff: 2^3 * 60 = 8 * 60 = 480 seconds
            expected_next_retry = fixed_time + timedelta(seconds=480)
            assert sync_item.next_retry == expected_next_retry
            assert sync_item.error_message == 'Test error'
    
    def test_mark_retry_max_retries_exceeded(self, restaurant):
        """Test mark_retry when max retries exceeded"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            retry_count=5,
            max_retries=5
        )
        
        sync_item.mark_retry('Final error')
        
        assert sync_item.retry_count == 5  # Should not increment
        assert sync_item.status == 'FAILED'  # Should remain FAILED
    
    def test_mark_retry_exponential_backoff_limit(self, restaurant):
        """Test exponential backoff has upper limit"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            retry_count=10,  # This would give 2^10 * 60 = 1024 * 60 = 61440 seconds
            max_retries=20
        )
        
        with patch('apps.core.models.timezone.now') as mock_now:
            fixed_time = timezone.make_aware(timezone.datetime(2024, 1, 1, 12, 0, 0))
            mock_now.return_value = fixed_time
            
            sync_item.mark_retry('Test')
            
            # Should be capped at 3600 seconds (1 hour)
            expected_next_retry = fixed_time + timedelta(seconds=3600)
            assert sync_item.next_retry == expected_next_retry
    
    def test_sync_queue_meta_options(self):
        """Test SyncQueue Meta options"""
        assert SyncQueue._meta.db_table == 'sync_queue'
        
        # Check indexes
        index_fields = [tuple(idx.fields) for idx in SyncQueue._meta.indexes]
        assert ('restaurant', 'status', 'priority', 'created_at') in index_fields
        assert ('status', 'next_retry') in index_fields
        assert ('idempotency_key',) in index_fields


@pytest.mark.django_db
class TestActivityLogModel:
    """Unit tests for ActivityLog model"""
    
    def test_activity_log_creation(self, restaurant, test_user):
        """Test creating an ActivityLog"""
        log = ActivityLog.objects.create(
            restaurant=restaurant,
            level='INFO',
            module='SYNC_MANAGER',
            action='SYNC_STARTED',
            details={'sync_id': 'test-123'},
            user=test_user,
            ip_address='192.168.1.1'
        )
        
        assert log.restaurant == restaurant
        assert log.level == 'INFO'
        assert log.module == 'SYNC_MANAGER'
        assert log.action == 'SYNC_STARTED'
        assert log.details == {'sync_id': 'test-123'}
        assert log.user == test_user
        assert log.ip_address == '192.168.1.1'
    
    def test_activity_log_string_representation(self, restaurant):
        """Test string representation of ActivityLog"""
        log = ActivityLog.objects.create(
            restaurant=restaurant,
            level='ERROR',
            module='SYNC_MANAGER',
            action='SYNC_FAILED'
        )
        
        expected_str = "Error - SYNC_MANAGER - SYNC_FAILED"
        assert str(log) == expected_str
    
    def test_activity_log_level_choices(self):
        """Test ActivityLog level choices"""
        level_choices = dict(ActivityLog.LOG_LEVELS)
        expected_choices = {
            'DEBUG': 'Debug',
            'INFO': 'Info',
            'WARNING': 'Warning',
            'ERROR': 'Error',
            'CRITICAL': 'Critical',
        }
        assert level_choices == expected_choices
    
    def test_activity_log_module_choices(self):
        """Test ActivityLog module choices contain sync manager"""
        module_choices = dict(ActivityLog.MODULES)
        assert 'SYNC_MANAGER' in module_choices
        assert module_choices['SYNC_MANAGER'] == 'Sync Manager'