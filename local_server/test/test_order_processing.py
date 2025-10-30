#ORDER TESTS


import pytest
from decimal import Decimal
from apps.order_processing.services import OrderProcessingService
from apps.order_processing.models import OfflineOrder
from apps.core.models import SyncQueue

@pytest.mark.django_db
class TestOrderProcessing:
    
    def test_create_offline_order_success(self, test_restaurant):
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {'id': '1', 'name': 'Burger', 'price': '10.00', 'quantity': 2},
                {'id': '2', 'name': 'Fries', 'price': '5.00', 'quantity': 1},
            ],
            'table_id': '00000000-0000-0000-0000-000000000001',
            'special_instructions': 'No onions',
            'estimated_preparation_time': 15,
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert result['success'] is True
        assert 'order_id' in result
        assert 'otp_code' in result
        assert len(result['otp_code']) == 6
        
        # Verify order created
        order = OfflineOrder.objects.get(id=result['order_id'])
        assert order.total_amount == Decimal('27.00')  # (10*2 + 5) * 1.08 tax
        assert order.order_status == 'PENDING'
        assert order.sync_status == 'PENDING_SYNC'
        
        # Verify sync queue entry
        assert SyncQueue.objects.filter(
            restaurant=test_restaurant,
            sync_type='ORDER_CREATE'
        ).exists()
    
    def test_update_order_status(self, test_restaurant):
        service = OrderProcessingService()
        
        # Create order first
        order_data = {
            'items': [{'id': '1', 'name': 'Test', 'price': '10.00', 'quantity': 1}]
        }
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        # Update status
        success = service.update_order_status(order_id, 'PREPARING')
        
        assert success is True
        
        # Verify update
        order = OfflineOrder.objects.get(id=order_id)
        assert order.order_status == 'PREPARING'
        assert order.preparation_started_at is not None
        
        # Verify sync queue
        assert SyncQueue.objects.filter(
            restaurant=test_restaurant,
            sync_type='ORDER_UPDATE'
        ).exists()
    
    def test_calculate_totals_with_tax(self, test_restaurant):
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {'id': '1', 'name': 'Item1', 'price': '100.00', 'quantity': 1},
            ]
        }
        
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order = OfflineOrder.objects.get(id=result['order_id'])
        
        # 100 + 8% tax = 108
        assert order.total_amount == Decimal('108.00')
        assert order.tax_amount == Decimal('8.00')