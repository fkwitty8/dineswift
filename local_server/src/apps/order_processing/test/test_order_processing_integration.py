#Integration Tests
import pytest
import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta

from apps.order_processing.models import OfflineOrder, OrderCRDTState
from apps.order_processing.services import OrderProcessingService
from apps.core.models import Restaurant, SyncQueue

@pytest.mark.django_db
class TestOrderProcessingIntegration:
    """Integration tests for complete order processing workflow"""
    
    def test_complete_order_workflow(self, test_restaurant):
        """Test complete order workflow from creation to completion"""
        service = OrderProcessingService()
        
        # 1. Create order
        order_data = {
            'items': [
                {
                    'id': '1',
                    'name': 'Integration Burger',
                    'price': '12.00',
                    'quantity': 2
                }
            ],
            'table_id': '00000000-0000-0000-0000-000000000002',
            'special_instructions': 'No onions, extra cheese',
            'estimated_preparation_time': 15
        }
        
        create_result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert create_result['success'] is True
        order_id = create_result['order_id']
        
        # 2. Verify initial state
        order = OfflineOrder.objects.get(id=order_id)
        assert order.order_status == 'PENDING'
        assert order.sync_status == 'PENDING_SYNC'
        assert order.total_amount == Decimal('25.92')  # (12*2) * 1.08 tax
        assert order.special_instructions == 'No onions, extra cheese'
        assert order.estimated_preparation_time == 15
        
        # 3. Update through status flow
        service.update_order_status(order_id, 'CONFIRMED')
        order.refresh_from_db()
        assert order.order_status == 'CONFIRMED'
        
        service.update_order_status(order_id, 'PREPARING')
        order.refresh_from_db()
        assert order.order_status == 'PREPARING'
        assert order.preparation_started_at is not None
        
        service.update_order_status(order_id, 'READY')
        order.refresh_from_db()
        assert order.order_status == 'READY'
        
        service.update_order_status(order_id, 'COMPLETED')
        order.refresh_from_db()
        assert order.order_status == 'COMPLETED'
        assert order.completed_at is not None
        
        # 4. Verify sync queue entries were created for each update
        sync_entries = SyncQueue.objects.filter(restaurant=test_restaurant)
        assert sync_entries.count() >= 4  # At least one for create and each status update
    
    def test_order_with_complex_modifiers(self, test_restaurant):
        """Test order creation with complex modifiers and special instructions"""
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {
                    'id': '1',
                    'name': 'Ultimate Burger',
                    'price': '15.00',
                    'quantity': 1,
                    'modifiers': [
                        {'name': 'Extra Cheese', 'price': '2.00'},
                        {'name': 'Bacon', 'price': '3.00'},
                        {'name': 'Avocado', 'price': '2.50'},
                        {'name': 'Fried Egg', 'price': '2.00'}
                    ],
                    'special_instructions': 'Well done, no pickles'
                },
                {
                    'id': '2',
                    'name': 'Loaded Fries',
                    'price': '8.00',
                    'quantity': 2,
                    'modifiers': [
                        {'name': 'Cheese Sauce', 'price': '1.50'},
                        {'name': 'Bacon Bits', 'price': '2.00'}
                    ]
                }
            ],
            'table_id': '00000000-0000-0000-0000-000000000003',
            'special_instructions': 'Separate checks please',
            'estimated_preparation_time': 20
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert result['success'] is True
        
        order = OfflineOrder.objects.get(id=result['order_id'])
        
        # Verify complex order structure
        assert len(order.order_items) == 2
        assert order.order_items[0]['name'] == 'Ultimate Burger'
        assert len(order.order_items[0]['modifiers']) == 4
        assert order.order_items[0]['special_instructions'] == 'Well done, no pickles'
        assert order.order_items[1]['name'] == 'Loaded Fries'
        assert order.order_items[1]['quantity'] == 2
        
        # Verify total calculation: (15+2+3+2.5+2) + (8+1.5+2)*2 = 24.5 + 23 = 47.5 * 1.08 = 51.30
        assert order.total_amount == Decimal('51.30')
        assert order.special_instructions == 'Separate checks please'
    
    def test_multiple_orders_same_table(self, test_restaurant):
        """Test creating multiple orders for the same table"""
        service = OrderProcessingService()
        table_id = '00000000-0000-0000-0000-000000000005'
        
        # Create multiple orders for the same table
        orders_data = [
            {
                'items': [{'id': '1', 'name': 'Burger', 'price': '10.00', 'quantity': 1}],
                'table_id': table_id
            },
            {
                'items': [{'id': '2', 'name': 'Pizza', 'price': '12.00', 'quantity': 1}],
                'table_id': table_id
            },
            {
                'items': [{'id': '3', 'name': 'Salad', 'price': '8.00', 'quantity': 2}],
                'table_id': table_id
            }
        ]
        
        created_orders = []
        for order_data in orders_data:
            result = service.create_offline_order(
                restaurant_id=str(test_restaurant.id),
                order_data=order_data
            )
            assert result['success'] is True
            created_orders.append(result['order_id'])
        
        # Verify all orders were created for the same table
        table_orders = OfflineOrder.objects.filter(
            restaurant=test_restaurant,
            table_id=table_id
        )
        assert table_orders.count() == 3
        
        # Verify each order has unique local_order_id
        order_ids = [order.local_order_id for order in table_orders]
        assert len(order_ids) == len(set(order_ids))  # All unique
    
    def test_order_lifecycle_with_sync(self, test_restaurant):
        """Test complete order lifecycle with sync status changes"""
        service = OrderProcessingService()
        
        # Create order
        order_data = {
            'items': [{'id': '1', 'name': 'Sync Test', 'price': '10.00', 'quantity': 1}]
        }
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        order = OfflineOrder.objects.get(id=order_id)
        assert order.sync_status == 'PENDING_SYNC'
        
        # Simulate starting sync
        order.sync_status = 'SYNCING'
        order.sync_attempts = 1
        order.last_sync_attempt = timezone.now()
        order.save()
        
        # Simulate successful sync
        order.sync_status = 'SYNCED'
        order.supabase_order_id = '00000000-0000-0000-0000-000000000999'
        order.save()
        
        order.refresh_from_db()
        assert order.sync_status == 'SYNCED'
        assert order.supabase_order_id is not None
        assert order.sync_attempts == 1
        
        # Simulate failed sync with error
        order.sync_status = 'SYNC_FAILED'
        order.sync_attempts = 2
        order.sync_error = 'Network timeout'
        order.save()
        
        order.refresh_from_db()
        assert order.sync_status == 'SYNC_FAILED'
        assert order.sync_error == 'Network timeout'
        assert order.sync_attempts == 2
    
    def test_bulk_order_processing_performance(self, test_restaurant):
        """Test performance with bulk order processing"""
        service = OrderProcessingService()
        
        import time
        start_time = time.time()
        
        # Create multiple orders in bulk
        batch_size = 10
        for i in range(batch_size):
            order_data = {
                'items': [
                    {
                        'id': f'{i}',
                        'name': f'Performance Item {i}',
                        'price': '10.00',
                        'quantity': 1
                    }
                ]
            }
            
            result = service.create_offline_order(
                restaurant_id=str(test_restaurant.id),
                order_data=order_data
            )
            assert result['success'] is True
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertion - should process orders efficiently
        assert total_time < 5.0  # 10 orders in under 5 seconds
        
        # Verify all orders created
        assert OfflineOrder.objects.filter(restaurant=test_restaurant).count() == batch_size
        
        # Verify all have unique local_order_id and OTP codes
        orders = OfflineOrder.objects.filter(restaurant=test_restaurant)
        local_ids = [order.local_order_id for order in orders]
        assert len(local_ids) == len(set(local_ids))  # All unique
    
    def test_order_with_crdt_integration(self, test_restaurant):
        service = OrderProcessingService()
        
        order_data = {
            'items': [{'id': '1', 'name': 'CRDT Test', 'price': '10.00', 'quantity': 1}]
        }
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        # Get the existing CRDT state (created by the service)
        order = OfflineOrder.objects.get(id=order_id)
        
        # Update the existing CRDT state instead of creating new one
        crdt_state = OrderCRDTState.objects.get(order=order)
        crdt_state.vector_clock['local_node'] = 2
        crdt_state.last_operation = 'STATUS_UPDATE'
        crdt_state.operation_timestamp = timezone.now()
        crdt_state.save()
        
        # Verify integration
        order.refresh_from_db()
        crdt_state.refresh_from_db()
        
        assert order.order_status == 'PENDING'  # Should still be PENDING
        assert crdt_state.vector_clock['local_node'] == 2
    
    def test_order_error_recovery(self, test_restaurant):
        service = OrderProcessingService()

        order_data = {
            'items': [{'id': '1', 'name': 'Recovery Test', 'price': '10.00', 'quantity': 1}]
        }

        # First attempt (simulate failure in calculate_subtotal)
        with patch.object(service, 'calculate_subtotal') as mock_calculate:
            mock_calculate.side_effect = Exception("Calculation error")

            result = service.create_offline_order(
                restaurant_id=str(test_restaurant.id),
                order_data=order_data
            )

            assert result['success'] is False

        # Second attempt (should succeed)
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )

        assert result['success'] is True
        
        def test_order_with_different_payment_methods(self, test_restaurant):
            """Test order creation with different payment methods"""
            service = OrderProcessingService()
            
            payment_methods = ['cash', 'card', 'momo', 'account']
            
            for method in payment_methods:
                order_data = {
                    'items': [{'id': '1', 'name': f'{method} Test', 'price': '10.00', 'quantity': 1}],
                    'payment_method': method
                }
                
                if method == 'momo':
                    order_data['customer_phone'] = '+1234567890'
                
                result = service.create_offline_order(
                    restaurant_id=str(test_restaurant.id),
                    order_data=order_data
                )
                
                assert result['success'] is True
                
                # Verify order was created
                order = OfflineOrder.objects.get(id=result['order_id'])
                assert order is not None

@pytest.mark.django_db
class TestOrderEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_order_with_maximum_quantities(self, test_restaurant):
        """Test order creation with maximum reasonable quantities"""
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {'id': '1', 'name': 'Max Qty Item', 'price': '0.01', 'quantity': 999},
                {'id': '2', 'name': 'Expensive Item', 'price': '9999.99', 'quantity': 1}
            ]
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert result['success'] is True
        
        order = OfflineOrder.objects.get(id=result['order_id'])
        # Should handle large quantities and prices without issues
        assert order.total_amount > Decimal('0.00')
    
    def test_order_with_special_characters(self, test_restaurant):
        """Test order creation with special characters in names and instructions"""
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {
                    'id': '1',
                    'name': 'Burger 🍔 with Emoji',
                    'price': '10.00',
                    'quantity': 1,
                    'special_instructions': 'Extra spicy 🌶️🌶️🌶️'
                }
            ],
            'special_instructions': 'Table #42 • Window seat 🪟'
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert result['success'] is True
        
        order = OfflineOrder.objects.get(id=result['order_id'])
        assert '🍔' in order.order_items[0]['name']
        assert '🌶️' in order.order_items[0]['special_instructions']
        assert '🪟' in order.special_instructions
    
    def test_order_status_workflow_validation(self, test_restaurant):
        """Test all valid status transitions in workflow"""
        service = OrderProcessingService()
        
        # Create order
        order_data = {
            'items': [{'id': '1', 'name': 'Workflow Test', 'price': '10.00', 'quantity': 1}]
        }
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        # Test valid workflow: PENDING -> CONFIRMED -> PREPARING -> READY -> COMPLETED
        valid_transitions = [
            ('CONFIRMED', True),
            ('PREPARING', True),
            ('READY', True),
            ('COMPLETED', True)
        ]
        
        for new_status, should_succeed in valid_transitions:
            success = service.update_order_status(order_id, new_status)
            assert success == should_succeed
            
            if should_succeed:
                order = OfflineOrder.objects.get(id=order_id)
                assert order.order_status == new_status
        
        # Test cancellation from different states
        order_data2 = {
            'items': [{'id': '1', 'name': 'Cancel Test', 'price': '10.00', 'quantity': 1}]
        }
        result2 = service.create_offline_order(str(test_restaurant.id), order_data2)
        cancel_order_id = result2['order_id']
        
        # Cancel from PENDING state
        success = service.update_order_status(cancel_order_id, 'CANCELLED')
        assert success is True
        
        order = OfflineOrder.objects.get(id=cancel_order_id)
        assert order.order_status == 'CANCELLED'

@pytest.mark.django_db
class TestOrderDataConsistency:
    """Test data consistency and integrity"""
    
    def test_order_data_persistence(self, test_restaurant):
        """Test that order data persists correctly through updates"""
        service = OrderProcessingService()
        
        # Create order
        original_items = [
            {'id': '1', 'name': 'Persistent Burger', 'price': '10.00', 'quantity': 2},
            {'id': '2', 'name': 'Persistent Fries', 'price': '5.00', 'quantity': 1}
        ]
        
        order_data = {
            'items': original_items,
            'table_id': '00000000-0000-0000-0000-000000000007',
            'special_instructions': 'Original instructions'
        }
        
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        # Update status multiple times
        service.update_order_status(order_id, 'CONFIRMED')
        service.update_order_status(order_id, 'PREPARING')
        
        # Verify original data is preserved
        order = OfflineOrder.objects.get(id=order_id)
        assert order.order_items == original_items
        assert str(order.table_id)== '00000000-0000-0000-0000-000000000007'
        assert order.special_instructions == 'Original instructions'
        assert order.total_amount == Decimal('27.00')  # Should not change
    
    def test_order_unique_constraints(self, test_restaurant):
        """Test order unique constraints"""
        service = OrderProcessingService()
        
        # Create first order
        order_data = {
            'items': [{'id': '1', 'name': 'Unique Test', 'price': '10.00', 'quantity': 1}]
        }
        
        result1 = service.create_offline_order(str(test_restaurant.id), order_data)
        assert result1['success'] is True
        
        # The service should handle local_order_id uniqueness
        # This might require mocking or testing the ID generation logic
        
    def test_order_audit_trail(self, test_restaurant):
        """Test that order audit trail is maintained"""
        service = OrderProcessingService()
        
        # Create order
        order_data = {
            'items': [{'id': '1', 'name': 'Audit Test', 'price': '10.00', 'quantity': 1}]
        }
        
        create_time = timezone.now()
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        order = OfflineOrder.objects.get(id=order_id)
        
        # Verify timestamps
        assert order.created_at >= create_time
        assert order.updated_at >= create_time
        
        # Update and verify updated_at changes
        import time
        time.sleep(0.1)  # Ensure time difference
        service.update_order_status(order_id, 'CONFIRMED')
        
        order.refresh_from_db()
        assert order.updated_at > order.created_at