#SYNC TESTS


import pytest
from unittest.mock import Mock, patch
from apps.sync_manager.services import SyncManager
from apps.core.models import SyncQueue
from apps.order_processing.models import OfflineOrder

@pytest.mark.django_db
class TestSyncManager:
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_sync_order_create_success(self, mock_supabase, test_restaurant):
        # Setup
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='ORD-20250101-0001',
            order_items=[],
            total_amount=Decimal('10.00'),
            tax_amount=Decimal('0.80'),
        )
        
        sync_item = SyncQueue.objects.create(
            restaurant=test_restaurant,
            sync_type='ORDER_CREATE',
            payload={'local_order_id': str(order.id)}
        )
        
        mock_supabase.sync_order.return_value = '00000000-0000-0000-0000-000000000001'
        
        # Execute
        manager = SyncManager()
        success = manager.process_sync_item(sync_item)
        
        # Verify
        assert success is True
        sync_item.refresh_from_db()
        assert sync_item.status == 'COMPLETED'
        
        order.refresh_from_db()
        assert order.sync_status == 'SYNCED'
        assert order.supabase_order_id is not None
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_sync_failure_with_retry(self, mock_supabase, test_restaurant):
        sync_item = SyncQueue.objects.create(
            restaurant=test_restaurant,
            sync_type='ORDER_CREATE',
            payload={}
        )
        
        mock_supabase.sync_order.side_effect = Exception('Network error')
        
        manager = SyncManager()
        success = manager.process_sync_item(sync_item)
        
        assert success is False
        sync_item.refresh_from_db()
        assert sync_item.status == 'FAILED'
        assert sync_item.retry_count == 1
        assert sync_item.next_retry is not None