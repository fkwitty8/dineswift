import pytest
import json
from unittest.mock import patch, Mock, MagicMock
from django.utils import timezone
from datetime import timedelta, datetime

from apps.core.models import SyncQueue
from apps.sync_manager.conflict_resolution import (
    ConflictDetector,
    ConflictResolver,
    ConflictResolutionStrategy
)
from apps.sync_manager.services import SyncManager


@pytest.mark.django_db
class TestConflictDetector:
    """Tests for ConflictDetector"""
    
    def test_detect_conflict_no_data(self):
        """Test conflict detection with no data"""
        detector = ConflictDetector()
        
        has_conflict, info = detector.detect_conflict({}, {})
        assert has_conflict == False
        assert info is None
        
        has_conflict, info = detector.detect_conflict({'test': 'data'}, None)
        assert has_conflict == False
        assert info is None
    
    def test_detect_conflict_same_data(self):
        """Test conflict detection with identical data"""
        detector = ConflictDetector()
        
        data = {
            'status': 'PENDING',
            'items': [{'id': '1', 'quantity': 2}],
            'sync_version': 1,
            'updated_at': '2024-01-01T10:00:00Z',
        }
        
        has_conflict, info = detector.detect_conflict(data, data)
        assert has_conflict == False
        assert info is None
    
    def test_detect_conflict_different_versions(self):
        """Test conflict detection with different versions"""
        detector = ConflictDetector()
        
        local = {
            'status': 'PENDING',
            'items': [{'id': '1', 'quantity': 2}],
            'sync_version': 1,
            'updated_at': '2024-01-01T10:00:00Z',
        }
        
        remote = {
            'status': 'COMPLETED',  # Different status
            'items': [{'id': '1', 'quantity': 2}],
            'sync_version': 2,
            'updated_at': '2024-01-01T11:00:00Z',
        }
        
        has_conflict, info = detector.detect_conflict(local, remote)
        assert has_conflict == True
        assert info is not None
        assert 'fields_in_conflict' in info
        assert len(info['fields_in_conflict']) > 0
        assert info['fields_in_conflict'][0]['field'] == 'status'
    
    def test_calculate_hash(self):
        """Test hash calculation for data"""
        detector = ConflictDetector()
        
        data1 = {'test': 'value', 'number': 123}
        data2 = {'test': 'value', 'number': 123}
        data3 = {'test': 'different', 'number': 123}
        
        hash1 = detector._calculate_hash(data1)
        hash2 = detector._calculate_hash(data2)
        hash3 = detector._calculate_hash(data3)
        
        assert hash1 == hash2  # Same data, same hash
        assert hash1 != hash3  # Different data, different hash
    
    def test_create_version_vector(self):
        """Test version vector creation"""
        detector = ConflictDetector()
        
        data = {'sync_version': 5, 'status': 'PENDING'}
        operation = 'LOCAL_UPDATE'
        
        vector = detector.create_version_vector(data, operation)
        
        assert vector['version'] == 5
        assert vector['operation'] == 'LOCAL_UPDATE'
        assert vector['source'] == 'local'
        assert 'timestamp' in vector
        assert 'checksum' in vector


@pytest.mark.django_db
class TestConflictResolver:
    """Tests for ConflictResolver"""
    
    def test_get_resolution_strategy_default(self, sync_queue_item):
        """Test default strategy selection"""
        resolver = ConflictResolver(Mock())
        
        strategy = resolver._get_resolution_strategy(sync_queue_item)
        assert strategy == ConflictResolutionStrategy.LAST_WRITE_WINS
    
    def test_get_resolution_strategy_specified(self, sync_queue_item):
        """Test specified strategy selection"""
        resolver = ConflictResolver(Mock())
        
        strategy = resolver._get_resolution_strategy(
            sync_queue_item, 
            'manual_intervention'
        )
        assert strategy == ConflictResolutionStrategy.MANUAL_INTERVENTION
    
    def test_get_resolution_strategy_invalid(self, sync_queue_item):
        """Test invalid strategy falls back to default"""
        resolver = ConflictResolver(Mock())
        
        strategy = resolver._get_resolution_strategy(sync_queue_item, 'invalid_strategy')
        assert strategy == ConflictResolutionStrategy.LAST_WRITE_WINS
    
    def test_get_resolution_strategy_from_conflict_data(self, sync_queue_item):
        """Test strategy selection from conflict data"""
        sync_queue_item.conflict_data = {
            'preferred_resolution': 'merge'
        }
        
        resolver = ConflictResolver(Mock())
        strategy = resolver._get_resolution_strategy(sync_queue_item)
        
        assert strategy == ConflictResolutionStrategy.MERGE
    
    def test_requires_manual_intervention_failed_attempts(self, sync_queue_item):
        """Test manual intervention required after multiple failed attempts"""
        sync_queue_item.conflict_data = {
            'resolution_attempts': [
                {'success': False},
                {'success': False},
                {'success': False},
            ]
        }
        
        resolver = ConflictResolver(Mock())
        requires = resolver._requires_manual_intervention(sync_queue_item)
        
        assert requires == True
    
    def test_requires_manual_intervention_critical_field(self, sync_queue_item):
        """Test manual intervention for critical field conflicts"""
        sync_queue_item.conflict_data = {
            'fields_in_conflict': [
                {
                    'field': 'total_amount',
                    'local': 100.0,
                    'remote': 150.0,  # 50% difference
                }
            ]
        }
        
        resolver = ConflictResolver(Mock())
        requires = resolver._requires_manual_intervention(sync_queue_item)
        
        assert requires == True
    
    def test_is_significant_difference_numeric(self):
        """Test significant difference detection for numeric values"""
        resolver = ConflictResolver(Mock())
        
        # 1% difference - not significant
        assert resolver._is_significant_difference(100.0, 101.0) == False
        
        # 2% difference - significant
        assert resolver._is_significant_difference(100.0, 102.0) == True
        
        # Zero value handling
        assert resolver._is_significant_difference(0, 1.0) == True
    
    def test_is_significant_difference_other_types(self):
        """Test significant difference detection for non-numeric values"""
        resolver = ConflictResolver(Mock())
        
        # Strings
        assert resolver._is_significant_difference('test', 'test') == False
        assert resolver._is_significant_difference('test', 'different') == True
        
        # Lists
        assert resolver._is_significant_difference([1, 2], [1, 2]) == False
        assert resolver._is_significant_difference([1, 2], [1, 3]) == True
    
    def test_merge_status(self):
        """Test status merging with hierarchy"""
        resolver = ConflictResolver(Mock())
        
        local = {'status': 'PENDING'}
        remote = {'status': 'COMPLETED'}
        
        merged = resolver._merge_status(local, remote)
        assert merged == 'COMPLETED'  # Higher in hierarchy
        
        local = {'status': 'DELIVERED'}
        remote = {'status': 'CONFIRMED'}
        
        merged = resolver._merge_status(local, remote)
        assert merged == 'DELIVERED'  # Higher in hierarchy
    
    def test_merge_items(self):
        """Test order items merging"""
        resolver = ConflictResolver(Mock())
        
        local_items = [
            {'item_id': '1', 'name': 'Item 1', 'quantity': 2},
            {'item_id': '2', 'name': 'Item 2', 'quantity': 1},
        ]
        
        remote_items = [
            {'item_id': '1', 'name': 'Item 1', 'quantity': 1},
            {'item_id': '3', 'name': 'Item 3', 'quantity': 3},
        ]
        
        merged = resolver._merge_items(local_items, remote_items)
        
        # Should have 3 unique items
        assert len(merged) == 3
        
        # Item 1 should have combined quantity (2 + 1 = 3)
        item1 = next(item for item in merged if item['item_id'] == '1')
        assert item1['quantity'] == 3
        
        # Item 2 should be present
        item2 = next(item for item in merged if item['item_id'] == '2')
        assert item2['quantity'] == 1
        
        # Item 3 should be present
        item3 = next(item for item in merged if item['item_id'] == '3')
        assert item3['quantity'] == 3
    
    def test_calculate_total(self):
        """Test total calculation from items"""
        resolver = ConflictResolver(Mock())
        
        items = [
            {'price': 10.0, 'quantity': 2},
            {'price': 5.0, 'quantity': 3},
            {'price': 2.5, 'quantity': 4},
        ]
        
        total = resolver._calculate_total(items)
        expected = (10 * 2) + (5 * 3) + (2.5 * 4)
        assert total == expected
    
    def test_parse_timestamp(self):
        """Test timestamp parsing"""
        resolver = ConflictResolver(Mock())
        
        # ISO format
        dt = resolver._parse_timestamp('2024-01-01T10:00:00Z')
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        
        # Invalid timestamp
        dt = resolver._parse_timestamp('invalid')
        assert dt == timezone.make_aware(datetime.min)
        
        # None timestamp
        dt = resolver._parse_timestamp(None)
        assert dt == timezone.make_aware(datetime.min)


@pytest.mark.django_db
class TestConflictResolutionWorkflow:
    """Integration tests for complete conflict resolution workflow"""
    
    @patch('apps.sync_manager.conflict_resolution.SyncManager')
    def test_last_write_wins_local_wins(self, mock_sync_manager, sync_queue_item):
        """Test last-write-wins with local winning"""
        # Setup conflict data with local newer
        sync_queue_item.conflict_data = {
            'local_version': {'updated_at': '2024-01-01T12:00:00Z'},
            'remote_version': {'updated_at': '2024-01-01T11:00:00Z'},
            'resolution_attempts': [],
        }
        sync_queue_item.status = 'CONFLICT'
        sync_queue_item.save()
        
        # Mock sync manager
        mock_manager = Mock()
        mock_manager._force_push_to_supabase.return_value = True
        mock_sync_manager.return_value = mock_manager
        
        resolver = ConflictResolver(mock_manager)
        success, error, details = resolver.resolve_conflict(
            sync_queue_item,
            'last_write_wins'
        )
        
        assert success == True
        assert error is None
        assert details['strategy'] == 'last_write_wins'
        assert details['winner'] == 'local'
        mock_manager._force_push_to_supabase.assert_called_once()
    
    @patch('apps.sync_manager.conflict_resolution.SyncManager')
    def test_last_write_wins_remote_wins(self, mock_sync_manager, sync_queue_item, offline_order):
        """Test last-write-wins with remote winning"""
        # Setup conflict data with remote newer
        sync_queue_item.conflict_data = {
            'local_version': {'updated_at': '2024-01-01T11:00:00Z'},
            'remote_version': {'updated_at': '2024-01-01T12:00:00Z'},
            'resolution_attempts': [],
        }
        sync_queue_item.status = 'CONFLICT'
        sync_queue_item.payload = {'local_order_id': str(offline_order.id)}
        sync_queue_item.save()
        
        # Mock sync manager
        mock_manager = Mock()
        mock_manager._pull_from_supabase.return_value = True
        mock_sync_manager.return_value = mock_manager
        
        resolver = ConflictResolver(mock_manager)
        success, error, details = resolver.resolve_conflict(
            sync_queue_item,
            'last_write_wins'
        )
        
        assert success == True
        assert error is None
        assert details['strategy'] == 'last_write_wins'
        assert details['winner'] == 'remote'
        mock_manager._pull_from_supabase.assert_called_once()
    
    def test_manual_intervention_strategy(self, sync_queue_item):
        """Test manual intervention strategy"""
        resolver = ConflictResolver(Mock())
        success, error, details = resolver.resolve_conflict(
            sync_queue_item,
            'manual_intervention'
        )
        
        assert success == False  # Manual intervention doesn't resolve, it marks for review
        assert details['strategy'] == 'manual_intervention'
        assert details['action'] == 'marked_for_review'
        
        # Verify item is still in conflict state
        sync_queue_item.refresh_from_db()
        assert sync_queue_item.status == 'CONFLICT'
    
    @patch('apps.sync_manager.conflict_resolution.SyncManager')
    def test_merge_strategy(self, mock_sync_manager, sync_queue_item, offline_order):
        """Test merge strategy"""
        # Setup conflict data
        sync_queue_item.conflict_data = {
            'local_version': {
                'data': {
                    'status': 'PENDING',
                    'items': [{'item_id': '1', 'quantity': 2}],
                    'special_instructions': 'Local instructions',
                },
                'updated_at': '2024-01-01T11:00:00Z',
            },
            'remote_version': {
                'data': {
                    'status': 'COMPLETED',
                    'items': [{'item_id': '1', 'quantity': 1}, {'item_id': '2', 'quantity': 1}],
                    'special_instructions': 'Remote instructions',
                },
                'updated_at': '2024-01-01T12:00:00Z',
            },
            'resolution_attempts': [],
        }
        sync_queue_item.status = 'CONFLICT'
        sync_queue_item.payload = {'local_order_id': str(offline_order.id)}
        sync_queue_item.save()
        
        # Mock sync manager
        mock_manager = Mock()
        mock_manager._force_push_merged_data.return_value = True
        mock_sync_manager.return_value = mock_manager
        
        resolver = ConflictResolver(mock_manager)
        success, error, details = resolver.resolve_conflict(
            sync_queue_item,
            'merge'
        )
        
        assert success == True
        assert details['strategy'] == 'merge'
        assert 'merged_fields' in details
        assert 'conflicting_fields' in details
        mock_manager._force_push_merged_data.assert_called_once()
    
    @patch('apps.sync_manager.conflict_resolution.cache')
    def test_update_conflict_metrics(self, mock_cache, sync_queue_item):
        """Test conflict metrics updating"""
        resolver = ConflictResolver(Mock())
        
        # Mock cache
        mock_cache.get.return_value = {
            'total_conflicts': 5,
            'resolved_conflicts': 3,
            'failed_resolutions': 2,
            'by_strategy': {'last_write_wins': 3},
            'by_sync_type': {'ORDER_UPDATE': 5},
        }
        
        resolver._update_conflict_metrics(
            sync_queue_item,
            ConflictResolutionStrategy.LAST_WRITE_WINS,
            success=True
        )
        
        # Verify cache was updated
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        metrics = call_args[0][1]
        
        assert metrics['total_conflicts'] == 6
        assert metrics['resolved_conflicts'] == 4
        assert metrics['by_strategy']['last_write_wins'] == 4


@pytest.mark.django_db
class TestEnhancedSyncManagerConflictHandling:
    """Tests for enhanced conflict handling in SyncManager"""
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_detect_and_handle_conflicts(self, mock_supabase, sync_queue_item, offline_order):
        """Test conflict detection and handling"""
        # Setup
        sync_queue_item.sync_type = 'ORDER_UPDATE'
        sync_queue_item.payload = {
            'local_order_id': str(offline_order.id),
            'supabase_order_id': 'supabase-123',
            'updates': {'status': 'COMPLETED'}
        }
        sync_queue_item.save()
        
        # Mock Supabase to return conflicting data
        mock_supabase_client = Mock()
        mock_supabase_client.get_order.return_value = {
            'id': 'supabase-123',
            'status': 'PENDING',  # Different from local
            'items': offline_order.order_items,
            'total_amount': float(offline_order.total_amount),
            'tax_amount': float(offline_order.tax_amount),
            'special_instructions': 'Different instructions',
            'sync_version': offline_order.sync_version + 1,  # Different version
            'updated_at': (timezone.now() + timedelta(hours=1)).isoformat(),  # Newer
        }
        mock_supabase.supabase_client = mock_supabase_client
        
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
            manager.conflict_detector = ConflictDetector()
        
        # Detect conflicts
        conflict_detected = manager._detect_and_handle_conflicts(sync_queue_item)
        
        assert conflict_detected == True
        
        # Verify item was marked as conflict
        sync_queue_item.refresh_from_db()
        assert sync_queue_item.status == 'CONFLICT'
        assert sync_queue_item.conflict_data is not None
        assert 'local_version' in sync_queue_item.conflict_data
        assert 'remote_version' in sync_queue_item.conflict_data
        assert 'conflict_info' in sync_queue_item.conflict_data
    
    @patch('apps.sync_manager.services.supabase_client')
    def test_force_push_merged_data(self, mock_supabase, sync_queue_item, offline_order):
        """Test force pushing merged data"""
        sync_queue_item.sync_type = 'ORDER_UPDATE'
        sync_queue_item.payload = {
            'local_order_id': str(offline_order.id),
            'supabase_order_id': 'supabase-123',
        }
        sync_queue_item.save()
        
        merged_data = {
            'status': 'COMPLETED',
            'items': [{'item_id': '1', 'quantity': 2}],
            'total_amount': 20.0,
            'tax_amount': 2.0,
        }
        
        # Mock Supabase
        mock_supabase_client = Mock()
        mock_supabase_client.update_order.return_value = True
        mock_supabase.supabase_client = mock_supabase_client
        
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
            manager.supabase = mock_supabase_client
        
        success = manager._force_push_merged_data(sync_queue_item, merged_data)
        
        assert success == True
        mock_supabase_client.update_order.assert_called_once_with(
            'supabase-123', merged_data
        )
        
        # Verify local order was updated
        offline_order.refresh_from_db()
        assert offline_order.order_status == 'COMPLETED'
        assert offline_order.total_amount == 20.0
    
    def test_prepare_order_data(self, offline_order):
        """Test order data preparation"""
        with patch.object(SyncManager, '__init__', return_value=None):
            manager = SyncManager()
        
        data = manager._prepare_order_data(offline_order)
        
        assert data['id'] == str(offline_order.id)
        assert data['status'] == offline_order.order_status
        assert data['items'] == offline_order.order_items
        assert data['total_amount'] == float(offline_order.total_amount)
        assert 'sync_version' in data
        assert 'updated_at' in data