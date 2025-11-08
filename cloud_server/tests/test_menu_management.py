import pytest
from decimal import Decimal
from cloud_api.models import Restaurant, Menu, MenuItem, InventoryItem, MenuItemIngredient


@pytest.mark.django_db
class TestMenuManagement:
    
    @pytest.fixture
    def setup_data(self):
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        
        menu = Menu.objects.create(
            restaurant=restaurant,
            name='Main Menu'
        )
        
        return {'restaurant': restaurant, 'menu': menu}
    
    def test_create_menu_item(self, setup_data):
        """Test menu item creation"""
        menu_item = MenuItem.objects.create(
            menu=setup_data['menu'],
            item_name='Burger',
            sales_price=Decimal('12.99'),
            preparation_time=15
        )
        
        assert menu_item.item_name == 'Burger'
        assert menu_item.sales_price == Decimal('12.99')
        assert menu_item.is_available is True
    
    def test_menu_item_ingredients(self, setup_data):
        """Test menu item with ingredients"""
        menu_item = MenuItem.objects.create(
            menu=setup_data['menu'],
            item_name='Burger',
            sales_price=Decimal('12.99'),
            preparation_time=15
        )
        
        ingredient = InventoryItem.objects.create(
            restaurant=setup_data['restaurant'],
            item_name='Beef Patty',
            unit_of_measure='piece',
            current_stock=Decimal('100.000')
        )
        
        menu_ingredient = MenuItemIngredient.objects.create(
            menu_item=menu_item,
            inventory_item=ingredient,
            quantity_required=Decimal('1.000'),
            unit='piece'
        )
        
        assert menu_ingredient.quantity_required == Decimal('1.000')