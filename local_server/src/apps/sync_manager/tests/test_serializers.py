import pytest
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.models import SyncQueue, Restaurant
from apps.core.serializers import (
    SyncQueueSerializer,
    SyncQueueCreateSerializer,
    SyncQueueUpdateSerializer,
    SyncQueueCancelSerializer,
    SyncQueueRetrySerializer,
    SyncQueueStatsSerializer,
    SyncQueueMetricsSerializer,
    SyncQueueBulkCreateSerializer,
    SyncQueueExportSerializer,
    ActivityLogSerializer
)


@pytest.mark.django_db
class TestSyncQueueSerializer:
    """Unit tests for SyncQueue serializers"""

    def test_sync_queue_serializer_serialization(self, restaurant):
        """Test serialization of SyncQueue model"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            priority=1,
            payload={'local_order_id': 'test-123'},
            max_retries=3,
        )
        
        serializer = SyncQueueSerializer(instance=sync_item)
        data = serializer.data
        
        assert data['sync_type'] == 'ORDER_CREATE'
        assert data['status'] == 'PENDING'
        assert data['priority'] == 1
        assert data['restaurant_name'] == restaurant.name
        assert data['sync_type_display'] == 'Order Create'
        assert data['status_display'] == 'Pending'
        assert data['retry_count'] == 0
        assert data['max_retries'] == 3
    
    def test_sync_queue_serializer_valid_payload(self, restaurant):
        """Test validation of valid payload"""
        valid_data = {
            'restaurant': restaurant.id,
            'sync_type': 'ORDER_CREATE',
            'payload': {'local_order_id': '456', 'test': True},
            'priority': 3
        }
        
        serializer = SyncQueueSerializer(data=valid_data)
        assert serializer.is_valid() is True
    
    def test_sync_queue_serializer_invalid_payload(self, restaurant):
        """Test validation of invalid payload (not a dict)"""
        invalid_data = {
            'restaurant': restaurant.id,
            'sync_type': 'ORDER_CREATE',
            'payload': 'invalid-string-not-dict'  # Should fail
        }
        
        serializer = SyncQueueSerializer(data=invalid_data)
        assert serializer.is_valid() is False
        assert 'payload' in serializer.errors
    
    def test_sync_queue_serializer_read_only_fields(self, restaurant):
        """Test that read-only fields cannot be written"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            payload={'local_order_id': 'test-123'}
        )
        
        update_data = {
            'status': 'COMPLETED',
            'created_at': '2024-01-01T00:00:00Z'  # This should be ignored
        }
        
        serializer = SyncQueueSerializer(instance=sync_item, data=update_data, partial=True)
        assert serializer.is_valid() is True
        updated_item = serializer.save()
        
        # created_at should not change
        assert updated_item.created_at != '2024-01-01T00:00:00Z'


@pytest.mark.django_db
class TestSyncQueueCreateSerializer:
    """Unit tests for SyncQueueCreateSerializer"""
    
    def test_create_serializer_valid_data(self, restaurant):
        """Test valid creation data"""
        data = {
            'restaurant': restaurant.id,
            'sync_type': 'ORDER_CREATE',
            'priority': 3,
            'payload': {'local_order_id': '123'},
            'max_retries': 3
        }
        
        serializer = SyncQueueCreateSerializer(data=data)
        assert serializer.is_valid() is True
        
        # Test creation
        sync_item = serializer.save()
        assert sync_item.sync_type == 'ORDER_CREATE'
        assert sync_item.status == 'PENDING'  # Default status
        assert sync_item.idempotency_key is not None
        assert sync_item.retry_count == 0
    
    def test_create_serializer_invalid_sync_type(self, restaurant):
        """Test with invalid sync type"""
        data = {
            'restaurant': restaurant.id,
            'sync_type': 'INVALID_TYPE',
            'payload': {'local_order_id': '123'}
        }
        
        serializer = SyncQueueCreateSerializer(data=data)
        assert serializer.is_valid() is False
        assert 'sync_type' in serializer.errors
    
    def test_create_serializer_missing_order_id_for_order_sync(self, restaurant):
        """Test missing local_order_id for order sync types"""
        data = {
            'restaurant': restaurant.id,
            'sync_type': 'ORDER_CREATE',
            'payload': {'items': [{'id': 1}]}  # Missing local_order_id
        }
        
        serializer = SyncQueueCreateSerializer(data=data)
        assert serializer.is_valid() is False
        assert 'payload' in serializer.errors
    
    def test_create_serializer_auto_generated_idempotency_key(self, restaurant):
        """Test auto-generation of idempotency key"""
        data = {
            'restaurant': restaurant.id,
            'sync_type': 'ORDER_CREATE',
            'payload': {'local_order_id': '123'}
        }
        
        serializer = SyncQueueCreateSerializer(data=data)
        assert serializer.is_valid() is True
        
        sync_item = serializer.save()
        assert sync_item.idempotency_key is not None
    
    def test_create_serializer_all_sync_types(self, restaurant):
        """Test creation with all valid sync types"""
        valid_sync_types = ['ORDER_CREATE', 'ORDER_UPDATE', 'ORDER_DELETE', 
                           'MENU_UPDATE', 'INVENTORY_UPDATE']
        
        for sync_type in valid_sync_types:
            data = {
                'restaurant': restaurant.id,
                'sync_type': sync_type,
                'payload': {'test': 'data'}
            }
            
            # For order-related sync types, need local_order_id
            if sync_type.startswith('ORDER_'):
                data['payload']['local_order_id'] = '123'
            
            serializer = SyncQueueCreateSerializer(data=data)
            assert serializer.is_valid() is True, f"Failed for sync_type: {sync_type}"
            
            sync_item = serializer.save()
            assert sync_item.sync_type == sync_type


@pytest.mark.django_db
class TestSyncQueueUpdateSerializer:
    """Unit tests for SyncQueueUpdateSerializer"""
    
    def test_update_serializer_valid_status_change(self, restaurant):
        """Test valid status update"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': '123'}
        )
        
        data = {'status': 'PROCESSING'}
        serializer = SyncQueueUpdateSerializer(instance=sync_item, data=data)
        assert serializer.is_valid() is True
        
        updated = serializer.save()
        assert updated.status == 'PROCESSING'
    
    def test_update_serializer_cannot_update_completed(self, restaurant):
        """Test cannot update completed items"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='COMPLETED',
            payload={'local_order_id': '123'}
        )
        
        data = {'status': 'FAILED'}
        serializer = SyncQueueUpdateSerializer(instance=sync_item, data=data)
        assert serializer.is_valid() is False
        assert 'status' in serializer.errors
    
    def test_update_serializer_retry_count_limit(self, restaurant):
        """Test retry count validation"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            retry_count=2,
            max_retries=5
        )
        
        data = {'retry_count': 10}  # More than max_retries (5)
        serializer = SyncQueueUpdateSerializer(instance=sync_item, data=data)
        assert serializer.is_valid() is False
        assert 'retry_count' in serializer.errors
    
    def test_update_serializer_invalid_status(self, restaurant):
        """Test invalid status value"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': '123'}
        )
        
        data = {'status': 'INVALID_STATUS'}
        serializer = SyncQueueUpdateSerializer(instance=sync_item, data=data)
        assert serializer.is_valid() is False
        assert 'status' in serializer.errors
    
    def test_update_serializer_read_only_fields(self, restaurant):
        """Test that restaurant and sync_type cannot be updated"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            payload={'local_order_id': '123'}
        )
        
        data = {
            'restaurant': restaurant.id,  # Should be ignored
            'sync_type': 'ORDER_UPDATE',  # Should be ignored
            'status': 'PROCESSING'
        }
        
        serializer = SyncQueueUpdateSerializer(instance=sync_item, data=data)
        assert serializer.is_valid() is True
        
        updated = serializer.save()
        # Should remain unchanged
        assert updated.restaurant == restaurant
        assert updated.sync_type == 'ORDER_CREATE'
        assert updated.status == 'PROCESSING'


@pytest.mark.django_db
class TestSyncQueueCancelSerializer:
    """Unit tests for SyncQueueCancelSerializer"""
    
    def test_cancel_serializer_valid_for_pending(self, restaurant):
        """Test canceling a pending item"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': '123'}
        )
        
        serializer = SyncQueueCancelSerializer(data={'reason': 'User requested'})
        serializer.context = {'sync_item': sync_item}
        assert serializer.is_valid() is True
    
    def test_cancel_serializer_invalid_for_completed(self, restaurant):
        """Test canceling a completed item without force"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='COMPLETED',
            payload={'local_order_id': '123'}
        )
        
        serializer = SyncQueueCancelSerializer(data={})
        serializer.context = {'sync_item': sync_item}
        assert serializer.is_valid() is False
        assert 'status' in serializer.errors
    
    def test_cancel_serializer_force_cancel(self, restaurant):
        """Test force canceling any item"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='COMPLETED',
            payload={'local_order_id': '123'}
        )
        
        serializer = SyncQueueCancelSerializer(data={'force': True})
        serializer.context = {'sync_item': sync_item}
        assert serializer.is_valid() is True
    
    def test_cancel_serializer_with_reason(self, restaurant):
        """Test canceling with reason"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': '123'}
        )
        
        reason = "Test cancellation reason that is quite long and descriptive"
        serializer = SyncQueueCancelSerializer(data={'reason': reason})
        serializer.context = {'sync_item': sync_item}
        assert serializer.is_valid() is True


@pytest.mark.django_db
class TestSyncQueueRetrySerializer:
    """Unit tests for SyncQueueRetrySerializer"""
    
    def test_retry_serializer_valid_data(self):
        """Test valid retry serializer data"""
        data = {'immediate': True, 'max_items': 50}
        serializer = SyncQueueRetrySerializer(data=data)
        assert serializer.is_valid() is True
    
    def test_retry_serializer_invalid_max_items_low(self):
        """Test invalid max_items value (too low)"""
        serializer = SyncQueueRetrySerializer(data={'max_items': 0})
        assert serializer.is_valid() is False
        assert 'max_items' in serializer.errors
    
    def test_retry_serializer_invalid_max_items_high(self):
        """Test invalid max_items value (too high)"""
        serializer = SyncQueueRetrySerializer(data={'max_items': 2000})
        assert serializer.is_valid() is False
        assert 'max_items' in serializer.errors
    
    def test_retry_serializer_default_values(self):
        """Test default values"""
        serializer = SyncQueueRetrySerializer(data={})
        assert serializer.is_valid() is True
        assert serializer.validated_data['immediate'] is False
        assert serializer.validated_data['max_items'] == 100


@pytest.mark.django_db
class TestSyncQueueStatsSerializer:
    """Unit tests for SyncQueueStatsSerializer"""
    
    def test_stats_serializer(self):
        """Test stats serializer validation"""
        stats_data = {
            'total': 100,
            'pending': 10,
            'processing': 5,
            'completed': 70,
            'failed': 10,
            'conflict': 3,
            'cancelled': 2,
            'avg_retry_count': 1.5,
            'success_rate': 70.0
        }
        
        serializer = SyncQueueStatsSerializer(data=stats_data)
        assert serializer.is_valid() is True
        assert serializer.validated_data['total'] == 100
        assert serializer.validated_data['success_rate'] == 70.0
    
    def test_stats_serializer_missing_field(self):
        """Test stats serializer with missing field"""
        stats_data = {
            'total': 100,
            'pending': 10,
            # Missing other fields
        }
        
        serializer = SyncQueueStatsSerializer(data=stats_data)
        assert serializer.is_valid() is False


@pytest.mark.django_db
class TestSyncQueueMetricsSerializer:
    """Unit tests for SyncQueueMetricsSerializer"""
    
    def test_metrics_serializer(self):
        """Test metrics serializer"""
        metrics_data = {
            'sync_type': 'ORDER_CREATE',
            'total': 50,
            'pending': 5,
            'failed': 5,
            'avg_retry': 0.5
        }
        
        serializer = SyncQueueMetricsSerializer(data=metrics_data)
        assert serializer.is_valid() is True
        
        # Test success_rate calculation
        data = serializer.to_representation(metrics_data)
        assert 'success_rate' in data
        
        # Expected: (total - failed - pending) / total * 100
        # (50 - 5 - 5) / 50 * 100 = 40 / 50 * 100 = 80
        assert data['success_rate'] == 80.0
    
    def test_metrics_serializer_zero_total(self):
        """Test metrics serializer with zero total"""
        metrics_data = {
            'sync_type': 'ORDER_CREATE',
            'total': 0,
            'pending': 0,
            'failed': 0,
            'avg_retry': 0.0
        }
        
        serializer = SyncQueueMetricsSerializer(data=metrics_data)
        assert serializer.is_valid() is True
        
        data = serializer.to_representation(metrics_data)
        assert data['success_rate'] == 0.0


@pytest.mark.django_db
class TestSyncQueueBulkCreateSerializer:
    """Unit tests for SyncQueueBulkCreateSerializer"""
    
    def test_bulk_create_valid(self, restaurant):
        """Test valid bulk creation"""
        items_data = [
            {
                'restaurant': restaurant.id,
                'sync_type': 'ORDER_CREATE',
                'payload': {'local_order_id': '1'}
            },
            {
                'restaurant': restaurant.id,
                'sync_type': 'ORDER_UPDATE',
                'payload': {'local_order_id': '2'}
            }
        ]
        
        data = {'items': items_data}
        serializer = SyncQueueBulkCreateSerializer(data=data)
        assert serializer.is_valid() is True
    
    def test_bulk_create_too_many_items(self, restaurant):
        """Test bulk creation with too many items"""
        items_data = [{
            'restaurant': restaurant.id,
            'sync_type': 'ORDER_CREATE',
            'payload': {'local_order_id': str(i)}
        } for i in range(101)]  # More than 100
        
        data = {'items': items_data}
        serializer = SyncQueueBulkCreateSerializer(data=data)
        assert serializer.is_valid() is False
        assert 'items' in serializer.errors
    
    def test_bulk_create_empty_list(self):
        """Test bulk creation with empty list"""
        data = {'items': []}
        serializer = SyncQueueBulkCreateSerializer(data=data)
        assert serializer.is_valid() is True
    
    def test_bulk_create_mixed_valid_invalid(self, restaurant):
        """Test bulk creation with mixed valid and invalid items"""
        items_data = [
            {
                'restaurant': restaurant.id,
                'sync_type': 'ORDER_CREATE',
                'payload': {'local_order_id': '1'}  # Valid
            },
            {
                'restaurant': restaurant.id,
                'sync_type': 'INVALID_TYPE',  # Invalid
                'payload': {'local_order_id': '2'}
            }
        ]
        
        data = {'items': items_data}
        serializer = SyncQueueBulkCreateSerializer(data=data)
        assert serializer.is_valid() is False
        assert 'items' in serializer.errors


@pytest.mark.django_db
class TestSyncQueueExportSerializer:
    """Unit tests for SyncQueueExportSerializer"""
    
    def test_export_serializer(self, restaurant):
        """Test export serializer"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='COMPLETED',
            payload={'local_order_id': '123', 'items': [{'id': 1, 'name': 'Pizza'}]},
            max_retries=5
        )
        
        # Set created_at and updated_at to simulate processing time
        sync_item.created_at = timezone.now() - timedelta(minutes=5)
        sync_item.updated_at = timezone.now()
        sync_item.save()
        
        serializer = SyncQueueExportSerializer(instance=sync_item)
        data = serializer.data
        
        assert data['restaurant_name'] == restaurant.name
        assert data['restaurant_supabase_id'] == str(restaurant.supabase_restaurant_id)
        assert data['sync_type_display'] == 'Order Create'
        assert data['status_display'] == 'Completed'
        assert 'payload_size' in data
        assert isinstance(data['payload_size'], int)
        assert 'processing_time' in data
        assert isinstance(data['processing_time'], float)
        assert data['retry_count'] == 0
    
    def test_export_serializer_no_processing_time(self, restaurant):
        """Test export serializer for item not completed"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',  # Not completed
            payload={'local_order_id': '123'}
        )
        
        serializer = SyncQueueExportSerializer(instance=sync_item)
        data = serializer.data
        
        assert data['processing_time'] is None


@pytest.mark.django_db
class TestActivityLogSerializer:
    """Unit tests for ActivityLogSerializer"""
    
    def test_activity_log_serializer(self, restaurant, test_user):
        """Test ActivityLog serializer"""
        from apps.core.models import ActivityLog
        
        log = ActivityLog.objects.create(
            restaurant=restaurant,
            level='INFO',
            module='SYNC_MANAGER',
            action='SYNC_STARTED',
            details={'sync_id': 'test-123'},
            user=test_user,
            ip_address='192.168.1.1'
        )
        
        serializer = ActivityLogSerializer(instance=log)
        data = serializer.data
        
        assert data['restaurant'] == restaurant.id
        assert data['restaurant_name'] == restaurant.name
        assert data['level'] == 'INFO'
        assert data['module'] == 'SYNC_MANAGER'
        assert data['action'] == 'SYNC_STARTED'
        assert data['details'] == {'sync_id': 'test-123'}
        assert 'created_at' in data
    
    def test_activity_log_serializer_validation(self, restaurant):
        """Test ActivityLog serializer validation"""
        valid_data = {
            'restaurant': restaurant.id,
            'level': 'INFO',
            'module': 'SYNC_MANAGER',
            'action': 'TEST_ACTION',
            'details': {'test': 'data'}
        }
        
        serializer = ActivityLogSerializer(data=valid_data)
        assert serializer.is_valid() is True