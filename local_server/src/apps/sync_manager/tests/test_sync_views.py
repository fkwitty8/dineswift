import pytest
import json
from unittest.mock import patch, Mock
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta

from apps.core.models import SyncQueue, ActivityLog


@pytest.mark.django_db
class TestSyncViews:
    """Unit tests for sync manager views"""
    
    def test_get_sync_status_authenticated(self, authenticated_client, restaurant):
        """Test get_sync_status for authenticated user"""
        # Create test sync items
        SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING'
        )
        SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_UPDATE',
            status='COMPLETED'
        )
        SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='FAILED'
        )
        
        response = authenticated_client.get('/api/sync/status/')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'statistics' in response.data
        assert 'metrics_by_type' in response.data
        assert 'performance' in response.data
        assert 'success_rate' in response.data
        
        stats = response.data['statistics']
        assert stats['total'] == 3
        assert stats['pending'] == 1
        assert stats['completed'] == 1
        assert stats['failed'] == 1
    
    def test_get_sync_status_unauthorized(self):
        """Test get_sync_status without authentication"""
        client = APIClient()
        response = client.get('/api/sync/status/')
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_sync_queue_with_filters(self, authenticated_client, restaurant):
        """Test get_sync_queue with various filters"""
        # Create test data
        for i in range(5):
            SyncQueue.objects.create(
                restaurant=restaurant,
                sync_type='ORDER_CREATE',
                status='PENDING' if i < 3 else 'COMPLETED',
                payload={'local_order_id': f'test-{i}'}
            )
        
        # Test with status filter
        response = authenticated_client.get('/api/sync/queue/?status=PENDING')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data.get('results', response.data)) == 3
        
        # Test with sync_type filter
        response = authenticated_client.get('/api/sync/queue/?sync_type=ORDER_CREATE')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data.get('results', response.data)) == 5
    
    def test_get_sync_queue_pagination(self, authenticated_client, restaurant):
        """Test get_sync_queue pagination"""
        # Create many items
        for i in range(75):
            SyncQueue.objects.create(
                restaurant=restaurant,
                sync_type='ORDER_CREATE',
                status='PENDING',
                payload={'local_order_id': f'test-{i}'}
            )
        
        response = authenticated_client.get('/api/sync/queue/?page=2&page_size=25')
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check pagination response
        if 'results' in response.data:  # Paginated response
            assert len(response.data['results']) == 25
            assert response.data['count'] == 75
            assert response.data['next'] is not None
            assert response.data['previous'] is not None
        else:
            # Not paginated, but should have limited results
            assert len(response.data) <= 50
    
    def test_get_sync_queue_invalid_date(self, authenticated_client):
        """Test get_sync_queue with invalid date format"""
        response = authenticated_client.get('/api/sync/queue/?start_date=invalid-date')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
    
    @patch('apps.sync_manager.views.retry_failed_syncs')
    def test_retry_failed_syncs_view(self, mock_retry_task, authenticated_client):
        """Test retry_failed_syncs view"""
        mock_retry_task.delay.return_value = Mock(id='task-123')
        
        response = authenticated_client.post('/api/sync/retry-failed/', {
            'max_age_hours': 12,
            'sync_type': 'ORDER_CREATE'
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        assert response.data['task_id'] == 'task-123'
        assert response.data['parameters']['max_age_hours'] == 12
        
        mock_retry_task.delay.assert_called_once()
    
    @patch('apps.sync_manager.views.sync_pending_orders')
    def test_force_sync_view(self, mock_sync_task, authenticated_client):
        """Test force_sync view"""
        mock_sync_task.delay.return_value = Mock(id='task-456')
        
        response = authenticated_client.post('/api/sync/force-sync/', {
            'limit': 50,
            'sync_types': ['ORDER_CREATE', 'ORDER_UPDATE']
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        assert response.data['task_id'] == 'task-456'
        assert response.data['parameters']['limit'] == 50
        
        mock_sync_task.delay.assert_called_once_with(batch_size=50)
    
    @patch('apps.sync_manager.services.SyncManager')
    def test_get_sync_metrics(self, mock_sync_manager, authenticated_client, restaurant):
        """Test get_sync_metrics view"""
        # Mock metrics
        mock_manager = Mock()
        mock_manager.get_sync_metrics.return_value = {
            'ORDER_CREATE': {
                'total': 100,
                'successful': 95,
                'failed': 5,
                'total_duration': 5000,
            }
        }
        mock_sync_manager.return_value = mock_manager
        
        # Mock historical data
        with patch('apps.sync_manager.views.SyncQueue.objects.filter') as mock_filter:
            mock_filter.return_value.extra.return_value.values.return_value.annotate.return_value.order_by.return_value = [
                {'date': '2024-01-01', 'sync_type': 'ORDER_CREATE', 'total': 10, 'successful': 9, 'failed': 1}
            ]
            
            response = authenticated_client.get('/api/sync/metrics/?days=30')
            
            assert response.status_code == status.HTTP_200_OK
            assert 'metrics' in response.data
            assert 'historical' in response.data
            assert 'backlog' in response.data
            assert 'retry_statistics' in response.data
            assert response.data['time_range']['days'] == 30
    
    def test_cancel_sync_item_success(self, authenticated_client, restaurant):
        """Test cancel_sync_item view"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='PENDING',
            payload={'test': 'data'}
        )
        
        response = authenticated_client.post(f'/api/sync/cancel/{sync_item.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        
        sync_item.refresh_from_db()
        assert sync_item.status == 'CANCELLED'
        
        # Verify activity log was created
        assert ActivityLog.objects.filter(
            restaurant=restaurant,
            module='SYNC_MANAGER',
            action='SYNC_CANCELLED'
        ).exists()
    
    def test_cancel_sync_item_not_found(self, authenticated_client):
        """Test cancel_sync_item with non-existent item"""
        fake_id = '00000000-0000-0000-0000-000000000000'
        
        response = authenticated_client.post(f'/api/sync/cancel/{fake_id}/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
    
    def test_cancel_sync_item_already_completed(self, authenticated_client, restaurant):
        """Test cancel_sync_item for completed item"""
        sync_item = SyncQueue.objects.create(
            restaurant=restaurant,
            sync_type='ORDER_CREATE',
            status='COMPLETED',  # Already completed
            payload={'test': 'data'}
        )
        
        response = authenticated_client.post(f'/api/sync/cancel/{sync_item.id}/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'cannot be cancelled' in response.data['error']
    
    @patch('apps.sync_manager.views.health_check_sync')
    def test_admin_sync_overview_authenticated(self, mock_health_task, admin_client):
        """Test admin_sync_overview with admin user"""
        mock_health_task.delay.return_value = Mock(id='health-task-123')
        
        # Mock data
        with patch('apps.sync_manager.views.SyncQueue.objects') as mock_objects:
            mock_objects.aggregate.return_value = {
                'total': 1000,
                'pending': 50,
                'completed': 900,
                'failed': 50,
            }
            
            mock_objects.values.return_value.annotate.return_value.order_by.return_value = [
                {'restaurant__name': 'Test Restaurant', 'total': 100, 'pending': 5, 'failed': 5, 'success_rate': 90.0}
            ]
            
            mock_objects.filter.return_value.order_by.return_value = []
            
            response = admin_client.get('/api/sync/admin/overview/')
            
            assert response.status_code == status.HTTP_200_OK
            assert 'global_statistics' in response.data
            assert 'by_restaurant' in response.data
            assert 'recent_failures' in response.data
            assert 'health_check_task' in response.data
    
    def test_admin_sync_overview_unauthorized(self, authenticated_client):
        """Test admin_sync_overview without admin privileges"""
        response = authenticated_client.get('/api/sync/admin/overview/')
        
        assert response.status_code == status.HTTP_403_FORBIDDEN