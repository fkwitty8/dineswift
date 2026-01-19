import pytest
import json
import uuid
from unittest.mock import patch, Mock
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from concurrent.futures import ThreadPoolExecutor

from apps.core.models import SyncQueue, ActivityLog
from apps.sync_manager.services import SyncManager
from apps.sync_manager.tasks import sync_pending_orders


@pytest.mark.django_db
class TestSyncIntegration:
    """Integration tests for complete sync workflow"""
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_complete_sync_workflow(self, mock_supabase, authenticated_client, restaurant, offline_order):
        """Test complete sync workflow from API to background processing"""
        # Step 1: Create sync item via model
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={
                'local_order_id': str(offline_order.id),
                'metadata': {'source': 'test'}
            },
            priority=1
        )
        
        # Step 2: Check sync status API
        response = authenticated_client.get('/api/sync/status/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['statistics']['pending'] >= 1
        
        # Step 3: Check sync queue API
        response = authenticated_client.get('/api/sync/queue/')
        assert response.status_code == status.HTTP_200_OK
        
        # Find our item in the queue
        queue_data = response.data.get('results', response.data)
        item_in_queue = any(
            item['id'] == str(sync_item.id) 
            for item in queue_data
        )
        assert item_in_queue
        
        # Step 4: Process sync item manually (simulating task)
        # Mock Supabase response
        mock_supabase_client = Mock()
        mock_supabase_client.sync_order.return_value = 'supabase-integration-123'
        mock_supabase.supabase_client = mock_supabase_client
        
        # Create sync manager and process item
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.circuit_breaker = Mock()
            manager.circuit_breaker.call = Mock(return_value='supabase-integration-123')
            manager.max_retries = 5
            manager.batch_size = 100
        
        success, error = manager.process_sync_item(sync_item)
        
        assert success == True
        assert error is None
        
        # Step 5: Verify updates
        sync_item.refresh_from_db()
        assert sync_item.status == 'COMPLETED'
        assert sync_item.supabase_id == 'supabase-integration-123'
        
        offline_order.refresh_from_db()
        assert offline_order.supabase_order_id == 'supabase-integration-123'
        assert offline_order.sync_status == 'SYNCED'
        
        # Step 6: Verify activity logs
        assert ActivityLog.objects.filter(
            restaurant=restaurant,
            module='SYNC_MANAGER',
            action='SYNC_COMPLETED'
        ).exists()
        
        # Step 7: Check updated sync status
        response = authenticated_client.get('/api/sync/status/')
        assert response.data['statistics']['completed'] >= 1
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_sync_retry_workflow(self, mock_supabase, restaurant, offline_order):
        """Test sync retry workflow"""
        # Create sync item that will fail
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'local_order_id': str(offline_order.id)},
            max_retries=3
        )
        
        # Mock Supabase to fail
        mock_supabase_client = Mock()
        mock_supabase_client.sync_order.side_effect = Exception("Supabase timeout")
        mock_supabase.supabase_client = mock_supabase_client
        
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.circuit_breaker = Mock()
            manager.circuit_breaker.call = Mock(side_effect=Exception("Supabase timeout"))
            manager.max_retries = 3
            manager.batch_size = 100
        
        # First attempt - should fail
        success, error = manager.process_sync_item(sync_item)
        assert success == False
        assert 'Supabase timeout' in error
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'FAILED'
        assert sync_item.retry_count == 1
        assert sync_item.next_retry is not None
        
        # Verify failure was logged
        assert ActivityLog.objects.filter(
            restaurant=restaurant,
            module='SYNC_MANAGER',
            action='SYNC_FAILED',
            level='WARNING'
        ).exists()
        
        # Simulate retry after delay
        sync_item.next_retry = timezone.now() - timedelta(minutes=1)
        sync_item.save()
        
        # Mock Supabase to succeed on retry
        mock_supabase_client.sync_order.side_effect = None
        mock_supabase_client.sync_order.return_value = 'supabase-retry-123'
        manager.circuit_breaker.call = Mock(return_value='supabase-retry-123')
        
        # Retry attempt - should succeed
        success, error = manager.process_sync_item(sync_item)
        assert success == True
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'COMPLETED'
        assert sync_item.retry_count == 1  # Should not increment on success
    
    def test_concurrent_sync_operations(self, transactional_db, restaurant, test_user):
        """Test concurrent sync operations (thread-safe)"""
        results = []
        errors = []
        
        def create_and_sync(thread_id):
            client = APIClient()
            client.force_authenticate(user=test_user)
            
            try:
                # Create a unique order ID for this thread
                order_id = f'order-concurrent-{thread_id}'
                
                # Create sync item
                sync_item = SyncQueue.objects.create(
                    restaurant=restaurant,
                    sync_type='ORDER_CREATE',
                    status='PENDING',
                    payload={'local_order_id': order_id},
                    priority=thread_id
                )
                
                # Try to get sync status
                response = client.get('/api/sync/status/')
                
                if response.status_code == 200:
                    results.append((thread_id, 'success', response.data['statistics']['total']))
                else:
                    results.append((thread_id, 'status_failed', response.status_code))
                    
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_and_sync, i) for i in range(5)]
            
            for future in futures:
                future.result()
        
        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Verify all threads succeeded
        success_count = len([r for r in results if r[1] == 'success'])
        assert success_count == 5
        
        # Verify total count in database
        total_items = SyncQueue.objects.filter(restaurant=restaurant).count()
        assert total_items == 5
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_batch_sync_processing(self, mock_supabase, restaurant):
        """Test batch processing of sync items"""
        # Create multiple sync items
        sync_items = []
        for i in range(10):
            item = SyncQueue.objects.create(
                restaurant=restaurant,
                sync_type='ORDER_CREATE',
                status='PENDING',
                payload={'local_order_id': f'batch-test-{i}'},
                sync_version=0
            )
            sync_items.append(item)
        
        # Mock Supabase
        mock_supabase_client = Mock()
        mock_supabase_client.sync_order.return_value = 'supabase-batch-123'
        mock_supabase.supabase_client = mock_supabase_client
        
        # Create sync manager
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.circuit_breaker = Mock()
            manager.circuit_breaker.call = Mock(return_value='supabase-batch-123')
            manager.max_retries = 5
            manager.batch_size = 100
        
        # Process batch
        results = manager.process_batch(sync_items)
        
        assert results['total'] == 10
        # In this test, all should fail because orders don't exist
        # but the manager will handle the DoesNotExist exception
        assert results['failed'] == 10
    
    def test_sync_metrics_integration(self, authenticated_client, restaurant):
        """Test sync metrics integration"""
        # Create sync items with different statuses and timestamps
        now = timezone.now()
        
        for i in range(20):
            status = 'COMPLETED' if i < 15 else 'FAILED'
            created_at = now - timedelta(hours=i)
            
            SyncQueue.objects.create(
                restaurant=restaurant,
                sync_type='ORDER_CREATE',
                status=status,
                payload={'local_order_id': f'metrics-test-{i}'},
                created_at=created_at,
                retry_count=0 if status == 'COMPLETED' else 2
            )
        
        # Get metrics
        response = authenticated_client.get('/api/sync/metrics/?days=7')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'metrics' in response.data
        assert 'historical' in response.data
        assert 'backlog' in response.data
        assert 'retry_statistics' in response.data
        
        # Verify time range
        assert response.data['time_range']['days'] == 7
        
        # Verify backlog
        if 'backlog' in response.data:
            backlog = response.data['backlog']
            # Should have at least ORDER_CREATE in backlog
            assert any(item.get('sync_type') == 'ORDER_CREATE' for item in backlog)
    
    @patch('apps.sync_manager.tasks.SyncManager')
    @patch('apps.sync_manager.tasks.SyncQueue')
    def test_task_integration(self, mock_sync_queue, mock_sync_manager, celery_app, restaurant):
        """Test Celery task integration"""
        # Mock sync items
        mock_item = Mock()
        mock_item.id = uuid.uuid4()
        
        mock_sync_queue.objects.filter.return_value.select_for_update.return_value = [mock_item]
        
        # Mock manager
        mock_manager = Mock()
        mock_manager.process_sync_item.return_value = (True, None)
        mock_sync_manager.return_value = mock_manager
        
        # Execute task
        result = sync_pending_orders.apply().get()
        
        assert result['status'] == 'completed'
        assert result['synced'] == 1
        assert result['failed'] == 0
        
        # Verify manager was called
        mock_manager.process_sync_item.assert_called_once_with(mock_item)