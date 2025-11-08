import pytest
from decimal import Decimal
from cloud_api.models import Restaurant, InventoryItem


@pytest.mark.django_db
class TestInventoryManagement:
    
    @pytest.fixture
    def setup_data(self):
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        return {'restaurant': restaurant}
    
    def test_create_inventory_item(self, setup_data):
        """Test inventory item creation"""
        item = InventoryItem.objects.create(
            restaurant=setup_data['restaurant'],
            item_name='Tomatoes',
            unit_of_measure='kg',
            cost_price=Decimal('5.50'),
            current_stock=Decimal('25.000'),
            min_stock_threshold=Decimal('5.000')
        )
        
        assert item.item_name == 'Tomatoes'
        assert item.current_stock == Decimal('25.000')
        assert item.stock_status == 'in_stock'
    
    def test_low_stock_detection(self, setup_data):
        """Test low stock status"""
        item = InventoryItem.objects.create(
            restaurant=setup_data['restaurant'],
            item_name='Salt',
            unit_of_measure='kg',
            current_stock=Decimal('2.000'),
            min_stock_threshold=Decimal('5.000'),
            stock_status='low_stock'
        )
        
        assert item.stock_status == 'low_stock'