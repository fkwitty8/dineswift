import pytest
import uuid
from unittest.mock import patch, Mock, MagicMock
from django.utils import timezone
from celery import states
from datetime import timedelta

from apps.core.models import SyncQueue, ActivityLog
from apps.sync_manager.tasks import (
    sync_pending_orders,
    retry_failed_syncs,
    resolve_conflicts,
    health_check_sync,
    SyncTask
)


@pytest.mark.django_db
class TestSyncTasks:
    """Unit tests for sync manager Celery tasks"""
    
    @patch('apps.sync_manager.tasks.SyncManager')
    def test_sync_pending_orders_no_items(self, mock_sync_manager, celery_app):
        """Test sync_pending_orders with no pending items"""
        # Mock the task
        task = sync_pending_orders
        task.request = Mock()
        task.request.id = 'test-task-123'
        
        # Mock manager
        mock_manager = Mock()
        mock_sync_manager.return_value = mock_manager
        
        result = task.apply().get()
        
        assert result['status'] == 'completed'
        assert result['synced'] == 0
        assert result['failed'] == 0
        assert 'task_id' in result
    
    @patch('apps.sync_manager.tasks.SyncManager')
    @patch('apps.sync_manager.tasks.SyncQueue')
    def test_sync_pending_orders_with_items(self, mock_sync_queue, mock_sync_manager, celery_app):
        """Test sync_pending_orders with pending items"""
        task = sync_pending_orders
        task.request = Mock()
        task.request.id = 'test-task-456'
        
        # Mock sync items
        mock_item1 = Mock()
        mock_item1.id = uuid.uuid4()
        mock_item2 = Mock()
        mock_item2.id = uuid.uuid4()
        
        mock_sync_queue.objects.filter.return_value.select_for_update.return_value = [
            mock_item1, mock_item2
        ]
        
        # Mock manager
        mock_manager = Mock()
        mock_manager.process_sync_item.side_effect = [
            (True, None),
            (False, 'Failed to sync')
        ]
        mock_sync_manager.return_value = mock_manager
        
        result = task.apply().get()
        
        assert result['status'] == 'completed'
        assert result['total'] == 2
        assert result['synced'] == 1
        assert result['failed'] == 1
        assert len(result['failed_items']) == 1
    
    @patch('apps.sync_manager.tasks.SyncManager')
    @patch('apps.sync_manager.tasks.SyncQueue')
    def test_sync_pending_orders_database_error(self, mock_sync_queue, mock_sync_manager, celery_app):
        """Test sync_pending_orders with database error"""
        task = sync_pending_orders
        task.request = Mock()
        task.request.id = 'test-task-789'
        task.retry = Mock()
        
        # Mock database error
        mock_sync_queue.objects.filter.side_effect = Exception("Database connection failed")
        
        task.apply()
        
        # Should retry on database error
        task.retry.assert_called_once()
    
    @patch('apps.sync_manager.tasks.SyncManager')
    @patch('apps.sync_manager.tasks.SyncQueue')
    def test_retry_failed_syncs(self, mock_sync_queue, mock_sync_manager, celery_app):
        """Test retry_failed_syncs task"""
        task = retry_failed_syncs
        task.request = Mock()
        task.request.id = 'retry-task-123'
        
        # Mock failed items
        mock_item1 = Mock()
        mock_item1.id = uuid.uuid4()
        mock_item2 = Mock()
        mock_item2.id = uuid.uuid4()
        
        mock_sync_queue.objects.filter.return_value = [mock_item1, mock_item2]
        
        # Mock abandoned items
        mock_abandoned = Mock()
        mock_abandoned.update.return_value = 1
        mock_sync_queue.objects.filter.return_value.filter.return_value = mock_abandoned
        
        # Mock manager
        mock_manager = Mock()
        mock_manager.process_sync_item.side_effect = [
            (True, None),
            (False, 'Still failing')
        ]
        mock_sync_manager.return_value = mock_manager
        
        result = task.apply().get()
        
        assert result['retried'] == 2
        assert result['abandoned'] == 1
        assert len(result['results']) == 2
    
    @patch('apps.sync_manager.tasks.SyncManager')
    @patch('apps.sync_manager.tasks.SyncQueue')
    def test_resolve_conflicts(self, mock_sync_queue, mock_sync_manager, celery_app):
        """Test resolve_conflicts task"""
        task = resolve_conflicts
        task.request = Mock()
        task.request.id = 'conflict-task-123'
        
        # Mock conflict items
        mock_item1 = Mock()
        mock_item1.id = uuid.uuid4()
        mock_item2 = Mock()
        mock_item2.id = uuid.uuid4()
        
        mock_sync_queue.objects.filter.return_value.order_by.return_value = [
            mock_item1, mock_item2
        ]
        
        # Mock manager
        mock_manager = Mock()
        mock_manager.resolve_conflict.side_effect = [True, False]
        mock_sync_manager.return_value = mock_manager
        
        result = task.apply().get()
        
        assert result['resolved'] == 1
        assert result['failed'] == 1
        assert result['total'] == 2
    
    @patch('apps.sync_manager.tasks.supabase_client')
    @patch('apps.sync_manager.tasks.connection')
    @patch('apps.sync_manager.tasks.cache')
    @patch('apps.sync_manager.tasks.SyncQueue')
    def test_health_check_sync(self, mock_sync_queue, mock_cache, mock_connection, mock_supabase, celery_app):
        """Test health_check_sync task"""
        task = health_check_sync
        task.request = Mock()
        task.request.id = 'health-task-123'
        
        # Mock database check
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = [5]
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock cache check
        mock_cache.set.return_value = True
        mock_cache.get.return_value = 'ok'
        
        # Mock Supabase check
        mock_supabase_client = Mock()
        mock_supabase_client.health_check.return_value = True
        mock_supabase_client.is_available.return_value = True
        mock_supabase.supabase_client = mock_supabase_client
        
        # Mock queue check
        mock_sync_queue.objects.filter.return_value.count.return_value = 0
        
        result = task.apply().get()
        
        assert result['status'] == 'healthy'
        assert 'checks' in result
        assert 'database' in result['checks']
        assert 'cache' in result['checks']
        assert 'supabase' in result['checks']
        assert 'queue' in result['checks']
    
    @patch('apps.sync_manager.tasks.supabase_client')
    def test_health_check_sync_unhealthy(self, mock_supabase, celery_app):
        """Test health_check_sync with unhealthy components"""
        task = health_check_sync
        task.request = Mock()
        task.request.id = 'health-task-456'
        
        # Mock database error
        with patch('apps.sync_manager.tasks.connection.cursor', side_effect=Exception("DB error")):
            result = task.apply().get()
            
            assert result['status'] == 'unhealthy'
            assert result['checks']['database']['status'] == 'unhealthy'
    
    def test_sync_task_on_failure(self):
        """Test SyncTask on_failure handler"""
        task = SyncTask()
        task.name = 'test-task'
        
        # Mock logger
        with patch('apps.sync_manager.tasks.logger.error') as mock_logger:
            # Mock activity log
            with patch('apps.sync_manager.tasks.ActivityLog.objects.create') as mock_log_create:
                exc = Exception("Test failure")
                task_id = 'task-123'
                args = ['sync-123']
                
                task.on_failure(exc, task_id, args, {}, None)
                
                # Verify error was logged
                mock_logger.assert_called_once()
                
                # Verify activity log was created
                mock_log_create.assert_called_once_with(
                    level='ERROR',
                    module='CELERY',
                    action='SYNC_TASK_FAILED',
                    details={
                        'task_id': task_id,
                        'task_name': task.name,
                        'error': str(exc),
                        'sync_id': args[0],
                    }
                )
    
    def test_sync_task_on_success(self):
        """Test SyncTask on_success handler"""
        task = SyncTask()
        
        with patch('apps.sync_manager.tasks.logger.info') as mock_logger:
            task.on_success('result', 'task-123', [], {})
            
            mock_logger.assert_called_once_with('Sync task task-123 completed successfully')