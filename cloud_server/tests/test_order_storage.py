import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date, timedelta
from cloud_api.models import (
    User, Restaurant, Order, SalesOrder, SupplyOrder, OrderItem,
    MenuItem, InventoryItem, Supplier, RestaurantTable, Menu
)


@pytest.mark.django_db
class TestOrderStorage:
    
    @pytest.fixture
    def setup_data(self):
        """Setup test data"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            phone_number='+1234567890'
        )
        
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St', 'city': 'Test City'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        
        menu = Menu.objects.create(
            restaurant=restaurant,
            name='Test Menu'
        )
        
        menu_item = MenuItem.objects.create(
            menu=menu,
            item_name='Test Burger',
            sales_price=Decimal('15.99'),
            preparation_time=20
        )
        
        inventory_item = InventoryItem.objects.create(
            restaurant=restaurant,
            item_name='Beef Patty',
            unit_of_measure='kg',
            cost_price=Decimal('8.50'),
            current_stock=Decimal('50.000')
        )
        
        supplier = Supplier.objects.create(
            company_name='Test Supplier',
            contact_info={'phone': '+1234567890', 'email': 'supplier@test.com'}
        )
        
        table = RestaurantTable.objects.create(
            restaurant=restaurant,
            table_number='T1',
            qr_code='QR123456',
            capacity=4
        )
        
        return {
            'user': user,
            'restaurant': restaurant,
            'menu': menu,
            'menu_item': menu_item,
            'inventory_item': inventory_item,
            'supplier': supplier,
            'table': table
        }
    
    def test_create_sales_order(self, setup_data):
        """Test creating a sales order with items"""
        data = setup_data
        
        order = Order.objects.create(
            restaurant=data['restaurant'],
            order_type='sales',
            status='pending',
            total_amount=Decimal('31.98')
        )
        
        sales_order = SalesOrder.objects.create(
            order=order,
            customer_user=data['user'],
            order_subtype='dine_in',
            table=data['table'],
            estimated_preparation_time=25
        )
        
        order_item = OrderItem.objects.create(
            order=order,
            source_entity_id=data['menu_item'].id,
            source_entity_type='menu_item',
            quantity=Decimal('2.000'),
            unit_price=Decimal('15.99'),
            total_price=Decimal('31.98')
        )
        
        assert order.order_type == 'sales'
        assert order.status == 'pending'
        assert order.total_amount == Decimal('31.98')
        assert sales_order.order_subtype == 'dine_in'
        assert order_item.quantity == Decimal('2.000')
    
    def test_create_supply_order(self, setup_data):
        """Test creating a supply order"""
        data = setup_data
        
        order = Order.objects.create(
            restaurant=data['restaurant'],
            order_type='supply',
            status='pending',
            total_amount=Decimal('425.00')
        )
        
        supply_order = SupplyOrder.objects.create(
            order=order,
            supplier=data['supplier'],
            expected_delivery_date=date.today() + timedelta(days=3),
            delivery_status='pending',
            invoice_total=Decimal('425.00')
        )
        
        order_item = OrderItem.objects.create(
            order=order,
            source_entity_id=data['inventory_item'].id,
            source_entity_type='inventory_item',
            quantity=Decimal('50.000'),
            unit_price=Decimal('8.50'),
            total_price=Decimal('425.00')
        )
        
        assert supply_order.supplier == data['supplier']
        assert supply_order.delivery_status == 'pending'
        assert order_item.source_entity_type == 'inventory_item'
    
    def test_multiple_order_items(self, setup_data):
        """Test order with multiple items"""
        data = setup_data
        
        order = Order.objects.create(
            restaurant=data['restaurant'],
            order_type='sales',
            status='pending',
            total_amount=Decimal('47.97')
        )
        
        OrderItem.objects.create(
            order=order,
            source_entity_id=data['menu_item'].id,
            source_entity_type='menu_item',
            quantity=Decimal('2.000'),
            unit_price=Decimal('15.99'),
            total_price=Decimal('31.98')
        )
        
        menu_item2 = MenuItem.objects.create(
            menu=data['menu'],
            item_name='Test Fries',
            sales_price=Decimal('7.99'),
            preparation_time=10
        )
        
        OrderItem.objects.create(
            order=order,
            source_entity_id=menu_item2.id,
            source_entity_type='menu_item',
            quantity=Decimal('2.000'),
            unit_price=Decimal('7.99'),
            total_price=Decimal('15.98')
        )
        
        order_items = OrderItem.objects.filter(order=order)
        assert order_items.count() == 2
    
    def test_takeaway_order(self, setup_data):
        """Test takeaway order creation"""
        data = setup_data
        
        order = Order.objects.create(
            restaurant=data['restaurant'],
            order_type='sales',
            status='pending',
            total_amount=Decimal('15.99')
        )
        
        sales_order = SalesOrder.objects.create(
            order=order,
            customer_user=data['user'],
            order_subtype='takeaway',
            otp_code='123456'
        )
        
        assert sales_order.order_subtype == 'takeaway'
        assert sales_order.otp_code == '123456'
        assert sales_order.table is None