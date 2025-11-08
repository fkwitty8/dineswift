#!/usr/bin/env python
import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')
django.setup()

from cloud_api.models import Restaurant, Order, OrderItem, Menu, MenuItem, User, SalesOrder, RestaurantTable

def test_complete_order():
    """Test creating a complete order with items"""
    try:
        # Create user
        user = User.objects.create_user(
            username='testcustomer',
            email='customer@test.com',
            phone_number='+1234567890'
        )
        print(f"✅ Created user: {user.username}")
        
        # Create restaurant
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        print(f"✅ Created restaurant: {restaurant.name}")
        
        # Create menu and menu item
        menu = Menu.objects.create(
            restaurant=restaurant,
            name='Main Menu'
        )
        
        menu_item = MenuItem.objects.create(
            menu=menu,
            item_name='Burger',
            sales_price=Decimal('15.99'),
            preparation_time=20
        )
        print(f"✅ Created menu item: {menu_item.item_name}")
        
        # Create table
        table = RestaurantTable.objects.create(
            restaurant=restaurant,
            table_number='T1',
            qr_code='QR123456',
            capacity=4
        )
        print(f"✅ Created table: {table.table_number}")
        
        # Create order
        order = Order.objects.create(
            restaurant=restaurant,
            order_type='sales',
            status='pending',
            total_amount=Decimal('31.98')
        )
        print(f"✅ Created order: {order.id}")
        
        # Create sales order
        sales_order = SalesOrder.objects.create(
            order=order,
            customer_user=user,
            order_subtype='dine_in',
            table=table
        )
        print(f"✅ Created sales order: {sales_order.order_subtype}")
        
        # Create order item
        order_item = OrderItem.objects.create(
            order=order,
            source_entity_id=menu_item.id,
            source_entity_type='menu_item',
            quantity=Decimal('2.000'),
            unit_price=Decimal('15.99'),
            total_price=Decimal('31.98')
        )
        print(f"✅ Created order item: {order_item.quantity} x {menu_item.item_name}")
        
        # Query complete order
        complete_order = Order.objects.select_related('salesorder').get(id=order.id)
        items = OrderItem.objects.filter(order=complete_order)
        
        print(f"\n📋 Order Summary:")
        print(f"   Order ID: {complete_order.id}")
        print(f"   Customer: {complete_order.salesorder.customer_user.username}")
        print(f"   Table: {complete_order.salesorder.table.table_number}")
        print(f"   Items: {items.count()}")
        print(f"   Total: ${complete_order.total_amount}")
        
        # Clean up
        order_item.delete()
        sales_order.delete()
        order.delete()
        table.delete()
        menu_item.delete()
        menu.delete()
        restaurant.delete()
        user.delete()
        print("✅ Cleanup completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Complete order test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing complete order creation...")
    test_complete_order()