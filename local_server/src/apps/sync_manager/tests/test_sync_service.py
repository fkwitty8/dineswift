import pytest
import uuid
from unittest.mock import patch, Mock, MagicMock
from django.utils import timezone
from datetime import timedelta

from apps.core.models import SyncQueue, ActivityLog
from apps.sync_manager.services import SyncManager, CircuitBreaker
from apps.order_processing.models import OfflineOrder


@pytest.mark.django_db
class TestCircuitBreaker:
    """Unit tests for CircuitBreaker"""
    
    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in CLOSED state"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        mock_func = Mock(return_value="success")
        result = cb.call(mock_func)
        
        assert result == "success"
        assert cb.state == 'CLOSED'
        assert cb.failure_count == 0
        mock_func.assert_called_once()
    
    def test_circuit_breaker_failure(self):
        """Test circuit breaker on failure"""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        
        mock_func = Mock(side_effect=Exception("Test error"))
        
        with pytest.raises(Exception):
            cb.call(mock_func)
        
        assert cb.failure_count == 1
        assert cb.state == 'CLOSED'  # Still closed
        
        # Second failure should open circuit
        with pytest.raises(Exception):
            cb.call(mock_func)
        
        assert cb.failure_count == 2
        assert cb.state == 'OPEN'
    
    def test_circuit_breaker_open_state(self):
        """Test circuit breaker rejects calls in OPEN state"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
        cb.state = 'OPEN'
        cb.last_failure_time = timezone.now().timestamp() - 30  # 30 seconds ago
        
        mock_func = Mock()
        
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(mock_func)
        
        mock_func.assert_not_called()
    
    def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker recovery"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30)
        cb.state = 'OPEN'
        cb.last_failure_time = timezone.now().timestamp() - 40  # 40 seconds ago (past timeout)
        
        mock_func = Mock(return_value="success")
        result = cb.call(mock_func)
        
        assert result == "success"
        assert cb.state == 'CLOSED'
        assert cb.failure_count == 0
    
    def test_circuit_breaker_half_open_failure(self):
        """Test circuit breaker failure in HALF_OPEN state"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=30)
        cb.state = 'HALF_OPEN'
        cb.failure_count = 1
        
        mock_func = Mock(side_effect=Exception("Test error"))
        
        with pytest.raises(Exception):
            cb.call(mock_func)
        
        assert cb.state == 'OPEN'
        assert cb.failure_count == 2


@pytest.mark.django_db
class TestSyncManagerServices:
    """Unit tests for SyncManager service"""
    
    def test_sync_manager_initialization(self, settings):
        """Test SyncManager initialization"""
        settings.SYNC_CONFIG = {
            'circuit_breaker_threshold': 3,
            'circuit_breaker_timeout': 120,
            'max_retries': 5,
            'batch_size': 100,
        }
        
        manager = SyncManager()
        
        assert manager.max_retries == 5
        assert manager.batch_size == 100
        assert isinstance(manager.circuit_breaker, CircuitBreaker)
        assert manager.circuit_breaker.failure_threshold == 3
        assert manager.circuit_breaker.recovery_timeout == 120
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_process_sync_item_order_create_success(self, mock_supabase, restaurant, offline_order):
        """Test successful ORDER_CREATE sync"""
        # Create sync item
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': str(offline_order.id)},
            sync_version=0
        )
        
        # Mock Supabase response
        mock_supabase_client = Mock()
        mock_supabase_client.sync_order.return_value = 'supabase-123'
        mock_supabase.supabase_client = mock_supabase_client
        
        # Mock circuit breaker
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.circuit_breaker = MagicMock()
            manager.circuit_breaker.call = Mock(return_value='supabase-123')
            manager.max_retries = 5
            manager.batch_size = 100
        
        success, error = manager.process_sync_item(sync_item)
        
        assert success == True
        assert error is None
        
        # Verify sync item was updated
        sync_item.refresh_from_db()
        assert sync_item.status == 'COMPLETED'
        assert sync_item.supabase_id == 'supabase-123'
        assert sync_item.error_message == ''
        
        # Verify order was updated
        offline_order.refresh_from_db()
        assert offline_order.supabase_order_id == 'supabase-123'
        assert offline_order.sync_status == 'SYNCED'
        
        # Verify activity log was created
        assert ActivityLog.objects.filter(
            restaurant=restaurant,
            module='SYNC_MANAGER',
            action='SYNC_COMPLETED'
        ).exists()
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_process_sync_item_order_create_missing_order(self, mock_supabase, restaurant):
        """Test ORDER_CREATE sync with non-existent order"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': str(uuid.uuid4())},  # Non-existent order
            sync_version=0
        )
        
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = Mock()
            manager.circuit_breaker = MagicMock()
            manager.max_retries = 5
            manager.batch_size = 100
        
        success, error = manager.process_sync_item(sync_item)
        
        assert success == False
        assert 'not found' in error
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'FAILED'
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_process_sync_item_order_update_success(self, mock_supabase, restaurant, offline_order):
        """Test successful ORDER_UPDATE sync"""
        # Set up order with Supabase ID
        offline_order.supabase_order_id = 'supabase-123'
        offline_order.save()
        
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_UPDATE',
            status='PENDING',
            payload={
                'local_order_id': str(offline_order.id),
                'supabase_order_id': 'supabase-123',
                'updates': {'status': 'COMPLETED'}
            },
            sync_version=0
        )
        
        # Mock Supabase response
        mock_supabase_client = Mock()
        mock_supabase_client.update_order.return_value = True
        mock_supabase.supabase_client = mock_supabase_client
        
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.circuit_breaker = MagicMock()
            manager.circuit_breaker.call = Mock(return_value=True)
            manager.max_retries = 5
            manager.batch_size = 100
        
        success, error = manager.process_sync_item(sync_item)
        
        assert success == True
        assert error is None
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'COMPLETED'
        
        offline_order.refresh_from_db()
        assert offline_order.sync_status == 'SYNCED'
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_process_sync_item_supabase_error(self, mock_supabase, restaurant, offline_order):
        """Test sync failure due to Supabase error"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': str(offline_order.id)},
            sync_version=0
        )
        
        # Mock Supabase to raise error
        mock_supabase_client = Mock()
        mock_supabase_client.sync_order.side_effect = Exception("Supabase connection failed")
        mock_supabase.supabase_client = mock_supabase_client
        
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.circuit_breaker = MagicMock()
            manager.circuit_breaker.call = Mock(side_effect=Exception("Supabase error"))
            manager.max_retries = 5
            manager.batch_size = 100
        
        success, error = manager.process_sync_item(sync_item)
        
        assert success == False
        assert 'Supabase error' in error
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'FAILED'
        assert sync_item.retry_count == 1
        assert sync_item.error_message == 'Supabase error'
    
    def test_process_batch(self, restaurant):
        """Test batch processing of sync items"""
        # Create multiple sync items
        sync_items = []
        for i in range(3):
            item = SyncQueue.objects.create(
                restaurant=restaurant,
                sync_type='ORDER_CREATE',
                status='PENDING',
                payload={'local_order_id': f'test-{i}'},
                sync_version=0
            )
            sync_items.append(item)
        
        # Mock process_sync_item to succeed for first 2, fail for last
        with patch.object(SyncManager, 'process_sync_item') as mock_process:
            mock_process.side_effect = [
                (True, None),
                (True, None),
                (False, 'Failed'),
            ]
            
            manager = SyncManager()
            results = manager.process_batch(sync_items)
            
            assert results['total'] == 3
            assert results['successful'] == 2
            assert results['failed'] == 1
            assert results['skipped'] == 0
    
    def test_handle_sync_failure_with_retry(self, restaurant):
        """Test handling sync failure with retry logic"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            max_retries=3,
            retry_count=0
        )
        
        manager = SyncManager()
        manager._handle_sync_failure(sync_item, 'Test error')
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'FAILED'
        assert sync_item.retry_count == 1
        assert sync_item.error_message == 'Test error'
        assert sync_item.next_retry is not None
        
        # Verify warning log was created
        assert ActivityLog.objects.filter(
            restaurant=restaurant,
            module='SYNC_MANAGER',
            action='SYNC_FAILED',
            level='WARNING'
        ).exists()
    
    def test_handle_sync_failure_max_retries(self, restaurant):
        """Test handling sync failure when max retries reached"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED',
            max_retries=3,
            retry_count=3  # Already at max
        )
        
        manager = SyncManager()
        manager._handle_sync_failure(sync_item, 'Final error')
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'FAILED'  # Should remain FAILED
        assert sync_item.retry_count == 3  # Should not increment
        
        # Verify error log was created
        assert ActivityLog.objects.filter(
            restaurant=restaurant,
            module='SYNC_MANAGER',
            action='SYNC_FAILED',
            level='ERROR'
        ).exists()
    
    @patch('apps.sync_manager.services.cache')
    def test_update_metrics(self, mock_cache, restaurant):
        """Test metrics update"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING'
        )
        
        mock_cache.get.return_value = {
            'total': 5,
            'successful': 4,
            'failed': 1,
            'total_duration': 5000,
        }
        
        manager = SyncManager()
        manager._update_metrics(sync_item, 100.5, success=True)
        
        expected_metrics = {
            'total': 6,
            'successful': 5,
            'failed': 1,
            'total_duration': 5100.5,
        }
        
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][1] == expected_metrics