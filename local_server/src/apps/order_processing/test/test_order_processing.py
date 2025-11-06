#Core Unit Tests
import pytest
import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.utils import timezone

from apps.order_processing.models import OfflineOrder, OrderCRDTState
from apps.order_processing.services import OrderProcessingService
from apps.order_processing.serializer import (
    OrderCreateSerializer, OrderSerializer, OrderStatusUpdateSerializer,
    OrderItemSerializer, OrderWithPaymentSerializer
)
from apps.core.models import Restaurant, SyncQueue

# Placeholder UUID for testing item ID validity
TEST_ITEM_UUID = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
ANOTHER_ITEM_UUID = 'b1f0d3e5-0a1c-4b3f-9e7d-7f8e9a0b1c2d'

@pytest.mark.django_db
class TestOrderModels:
    """Unit tests for Order Processing Models"""
    
    def test_offline_order_creation(self, test_restaurant):
        """Test creating OfflineOrder with all fields"""
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='TEST-001',
            order_items=[
                {
                    'id': TEST_ITEM_UUID ,
                    'name': 'Test Burger',
                    'price': '10.00',
                    'quantity': 2
                }
            ],
            total_amount=Decimal('21.60'),
            tax_amount=Decimal('1.60'),
            table_id='00000000-0000-0000-0000-000000000002',
            customer_id='00000000-0000-0000-0000-000000000003',
            special_instructions='No onions, extra cheese',
            order_status='PENDING',
            sync_status='PENDING_SYNC',
            estimated_preparation_time=15
        )
        
        assert order.restaurant == test_restaurant
        assert order.local_order_id == 'TEST-001'
        assert order.order_status == 'PENDING'
        assert order.sync_status == 'PENDING_SYNC'
        assert order.total_amount == Decimal('21.60')
        assert order.tax_amount == Decimal('1.60')
        assert order.special_instructions == 'No onions, extra cheese'
        assert order.estimated_preparation_time == 15
        assert str(order) == "Order TEST-001 - Pending"
    
    def test_order_status_choices(self, test_restaurant):
        """Test all order status choices"""
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='STATUS-TEST',
            order_items=[],
            total_amount=Decimal('10.00'),
            tax_amount=Decimal('0.80')
        )
        
        # Test valid status transitions
        valid_statuses = ['PENDING', 'CONFIRMED', 'PREPARING', 'READY', 'COMPLETED', 'CANCELLED']
        for status in valid_statuses:
            order.order_status = status
            order.save()
            assert order.order_status == status
    
    def test_sync_status_choices(self, test_restaurant):
        """Test all sync status choices"""
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='SYNC-TEST',
            order_items=[],
            total_amount=Decimal('10.00'),
            tax_amount=Decimal('0.80')
        )
        
        # Test valid sync statuses
        valid_sync_statuses = ['PENDING_SYNC', 'SYNCING', 'SYNCED', 'SYNC_FAILED', 'CONFLICT']
        for status in valid_sync_statuses:
            order.sync_status = status
            order.save()
            assert order.sync_status == status
    
    def test_order_crdt_state_creation(self, test_restaurant):
        """Test creating OrderCRDTState instance"""
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='CRDT-TEST',
            order_items=[],
            total_amount=Decimal('10.00'),
            tax_amount=Decimal('0.80')
        )
        
        crdt_state = OrderCRDTState.objects.create(
            order=order,
            vector_clock={'local_node': 1, 'cloud_node': 0},
            last_operation='ORDER_CREATE',
            operation_timestamp=timezone.now()
        )
        
        assert crdt_state.order == order
        assert crdt_state.vector_clock == {'local_node': 1, 'cloud_node': 0}
        assert crdt_state.last_operation == 'ORDER_CREATE'
        assert str(crdt_state) == "CRDT State for CRDT-TEST"
    
    def test_order_model_indexes(self, test_restaurant):
        """Test that model indexes work correctly"""
        # Create test data that should use indexes
        for i in range(3):
            OfflineOrder.objects.create(
                restaurant=test_restaurant,
                local_order_id=f'INDEX-TEST-{i}',
                order_items=[],
                total_amount=Decimal('10.00'),
                tax_amount=Decimal('0.80'),
                order_status='PENDING' if i % 2 == 0 else 'PREPARING',
                sync_status='PENDING_SYNC'
            )
        
        # Test queries that should use indexes
        pending_orders = OfflineOrder.objects.filter(
            restaurant=test_restaurant,
            order_status='PENDING'
        )
        assert pending_orders.count() == 2
        
        pending_sync_orders = OfflineOrder.objects.filter(
            restaurant=test_restaurant,
            sync_status='PENDING_SYNC'
        )
        assert pending_sync_orders.count() == 3

@pytest.mark.django_db
class TestOrderSerializers:
    """Unit tests for Order Serializers"""
    
    def test_order_item_serializer_basic(self):
        """Test basic OrderItemSerializer functionality"""
        # Data using the globally defined UUID for validity
        valid_data = {
            'id': TEST_ITEM_UUID, 
            'name': 'Test Item',
            'price': '15.00',
            'quantity': 2
        }
        
        # Test that serializer can handle basic data
        serializer = OrderItemSerializer(data=valid_data)
        assert serializer.is_valid(), serializer.errors
        
    def test_order_create_serializer_validation(self):
        """Test OrderCreateSerializer validation logic"""
        # Valid data
        valid_data = {
            'items': [
                {
                    'id': TEST_ITEM_UUID, # Using defined UUID here
                    'name': 'Burger',
                    'price': '10.00',
                    'quantity': 1
                }
            ],
            'table_id': '00000000-0000-0000-0000-000000000002',
            'payment_method': 'cash'
        }
        
        serializer = OrderCreateSerializer(data=valid_data)
        is_valid = serializer.is_valid()
        # Only access errors after calling is_valid()
        if not is_valid:
            print(serializer.errors)
        assert is_valid
        
        # Test empty items validation
        invalid_data = {'items': []}
        serializer = OrderCreateSerializer(data=invalid_data)
        is_valid = serializer.is_valid()
        assert not is_valid
        assert 'items' in serializer.errors
        
        # Test Momo payment validation (Requires customer_phone)
        momo_data = {
            # FIX: Changed 'id': '1' to use the valid UUID constant
            'items': [{'id': TEST_ITEM_UUID, 'name': 'Burger', 'price': '10.00', 'quantity': 1}],
            'payment_method': 'momo'
            # Missing customer_phone (this is the error we expect to catch now)
        }
        serializer = OrderCreateSerializer(data=momo_data)
        is_valid = serializer.is_valid()
        assert not is_valid
        # This assertion should now pass because the item ID validation is successful
        assert 'customer_phone' in serializer.errors
    
    def test_order_status_update_serializer(self, test_restaurant):
        """Test OrderStatusUpdateSerializer validation"""
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='STATUS-SERIALIZER',
            order_items=[],
            total_amount=Decimal('10.00'),
            tax_amount=Decimal('0.80'),
            order_status='PENDING'
        )
        
        # Test valid transition
        valid_data = {'status': 'CONFIRMED'}
        serializer = OrderStatusUpdateSerializer(instance=order, data=valid_data)
        assert serializer.is_valid()
        
        # Test invalid transition
        invalid_data = {'status': 'COMPLETED'}
        serializer = OrderStatusUpdateSerializer(instance=order, data=invalid_data)
        assert not serializer.is_valid()
    
    def test_order_serializer_output(self, test_restaurant):
        """Test OrderSerializer output format"""
        order = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id='SERIALIZER-OUTPUT',
            order_items=[
                {
                    # Use a valid ID for model instance creation
                    'id': TEST_ITEM_UUID, 
                    'name': 'Test Item',
                    'price': '10.00',
                    'quantity': 2
                }
            ],
            total_amount=Decimal('21.60'),
            tax_amount=Decimal('1.60'),
            order_status='PENDING'
        )
        
        serializer = OrderSerializer(order)
        data = serializer.data
        
        assert 'id' in data
        assert 'local_order_id' in data
        assert 'restaurant_name' in data
        assert 'total_amount' in data
        assert 'order_status' in data
        assert data['local_order_id'] == 'SERIALIZER-OUTPUT'

@pytest.mark.django_db
class TestOrderServices:
    """Unit tests for Order Processing Services"""
    
    @patch('apps.otp_service.services.OTPService.generate_otp')
    def test_update_order_status_success(self, mock_otp, test_restaurant):
        mock_otp.return_value = {
            'otp_code': '123456',
            'expires_at': '2024-01-01T00:00:00Z', 
            'otp_id': 'test-otp-id'
        }
        
        service = OrderProcessingService()
        
        # Create order first
        order_data = {
            # Use valid UUID for service call data
            'items': [{'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '10.00', 'quantity': 1}]
        }
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        # First transition to CONFIRMED (valid)
        success = service.update_order_status(order_id, 'CONFIRMED')
        assert success is True
        
        # Then transition to PREPARING (valid)
        success = service.update_order_status(order_id, 'PREPARING')
        assert success is True
        
        # Verify update
        order = OfflineOrder.objects.get(id=order_id)
        assert order.order_status == 'PREPARING'
    
    def test_update_order_status_invalid_transition(self, test_restaurant):
        """Test invalid order status transition"""
        service = OrderProcessingService()
        
        # Create order
        order_data = {
            # Use valid UUID for service call data
            'items': [{'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '10.00', 'quantity': 1}]
        }
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order_id = result['order_id']
        
        # Try invalid transition from PENDING to COMPLETED
        success = service.update_order_status(order_id, 'COMPLETED')
        
        # This should fail based on business rules
        assert success is False
        
        # Verify status didn't change
        order = OfflineOrder.objects.get(id=order_id)
        assert order.order_status == 'PENDING'
        assert order.completed_at is None
    
    def test_calculate_totals_with_tax(self, test_restaurant):
        """Test tax calculation in order creation"""
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                # Use valid UUID for service call data
                {'id': TEST_ITEM_UUID, 'name': 'Item1', 'price': '100.00', 'quantity': 1},
            ]
        }
        
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        order = OfflineOrder.objects.get(id=result['order_id'])
        
        # 100 + 8% tax = 108
        assert order.total_amount == Decimal('108.00')
        assert order.tax_amount == Decimal('8.00')
    
    def test_order_with_modifiers(self, test_restaurant):
        """Test order creation with item modifiers"""
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {
                    'id': TEST_ITEM_UUID, # Use valid UUID for service call data
                    'name': 'Custom Burger',
                    'price': '10.00',
                    'quantity': 1,
                    'modifiers': [
                        {'name': 'Extra Cheese', 'price': '2.00'},
                        {'name': 'Bacon', 'price': '3.00'}
                    ]
                }
            ]
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert result['success'] is True
        
        order = OfflineOrder.objects.get(id=result['order_id'])
        item = order.order_items[0]
        
        # Check modifiers are stored
        assert 'modifiers' in item
        assert len(item['modifiers']) == 2
        
        # Total should be (10 + 2 + 3) * 1.08 = 16.20
        assert order.total_amount == Decimal('16.20')

    def test_order_creation_with_empty_items(self, test_restaurant):
        """Test order creation with empty items list"""
        service = OrderProcessingService()
        
        order_data = {
            'items': []
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        assert result['success'] is False
        assert 'error' in result
    
    def test_order_creation_with_invalid_restaurant(self):
        """Test order creation with invalid restaurant ID"""
        service = OrderProcessingService()
        
        order_data = {
            # Use valid UUID for item ID, but invalid restaurant ID
            'items': [{'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '10.00', 'quantity': 1}]
        }
        
        result = service.create_offline_order(
            restaurant_id='00000000-0000-0000-0000-000000000999',  # Non-existent
            order_data=order_data
        )
        
        assert result['success'] is False
        assert 'error' in result
    
    @patch('apps.otp_service.services.OTPService.generate_otp')
    def test_otp_generation(self, mock_otp, test_restaurant):
        """Test OTP code generation"""
        
        mock_otp.return_value = {
            'otp_code': '654321', 
            'expires_at': '2024-01-01T00:00:00Z',
            'otp_id': 'test-otp-id'
        }
        
        service = OrderProcessingService()
        
        order_data = {
            # Use valid UUID for service call data
            'items': [{'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '10.00', 'quantity': 1}]
        }
        
        result = service.create_offline_order(str(test_restaurant.id), order_data)
        
        assert 'otp_code' in result
        # Check if otp_code is a dict or string and handle accordingly
        if isinstance(result['otp_code'], dict):
            assert 'otp_code' in result['otp_code']
            assert len(result['otp_code']['otp_code']) == 6
        else:
            assert len(result['otp_code']) == 6
    
@pytest.mark.django_db
class TestOrderErrorScenarios:
    """Test error handling scenarios"""
    
    def test_order_creation_with_invalid_data(self, test_restaurant):
        """Test order creation with various invalid data scenarios"""
        service = OrderProcessingService()
        
        test_cases = [
            # Missing items
            {'table_id': '00000000-0000-0000-0000-000000000001'},
            # Empty items
            {'items': []},
            # Item with negative price (Assuming serializer validates this)
            {'items': [{'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '-10.00', 'quantity': 1}]},
            # Item with zero quantity
            {'items': [{'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '10.00', 'quantity': 0}]},
        ]
        
        for invalid_data in test_cases:
            result = service.create_offline_order(
                restaurant_id=str(test_restaurant.id),
                order_data=invalid_data
            )
            
            # Should handle gracefully without crashing (return not None/failure dict)
            assert result is not None
    
    def test_update_nonexistent_order(self):
        """Test updating status of non-existent order"""
        service = OrderProcessingService()
        
        success = service.update_order_status(
            '00000000-0000-0000-0000-000000000999',  # Non-existent ID
            'PREPARING'
        )
        
        assert success is False
    
    def test_order_with_very_large_quantity(self, test_restaurant):
        """Test order creation with very large quantity"""
        service = OrderProcessingService()
        
        order_data = {
            'items': [
                {'id': TEST_ITEM_UUID, 'name': 'Test', 'price': '10.00', 'quantity': 1000}
            ]
        }
        
        result = service.create_offline_order(
            restaurant_id=str(test_restaurant.id),
            order_data=order_data
        )
        
        # Should handle large quantities
        assert result['success'] is True
        order = OfflineOrder.objects.get(id=result['order_id'])
        assert order.total_amount == Decimal('10800.00')  # 1000 * 10 * 1.08
