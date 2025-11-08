#!/usr/bin/env python
import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')
django.setup()

from cloud_api.models import Restaurant, Order

def test_simple_order():
    """Test simple order creation and retrieval"""
    try:
        # Create restaurant
        restaurant = Restaurant.objects.create(
            name='DB Test Restaurant',
            address={'street': '123 DB Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        print(f"✅ Created restaurant: {restaurant.name}")
        
        # Create order
        order = Order.objects.create(
            restaurant=restaurant,
            order_type='sales',
            status='pending',
            total_amount=Decimal('45.50'),
            notes='Database access test order'
        )
        print(f"✅ Created order successfully!")
        print(f"   Order ID: {order.id}")
        print(f"   Restaurant: {order.restaurant.name}")
        print(f"   Type: {order.order_type}")
        print(f"   Status: {order.status}")
        print(f"   Amount: ${order.total_amount}")
        print(f"   Created at: {order.created_at}")
        
        # Query all orders for this restaurant
        orders = Order.objects.filter(restaurant=restaurant)
        print(f"✅ Found {orders.count()} order(s) for restaurant")
        
        # Update order status
        order.status = 'confirmed'
        order.save()
        print(f"✅ Updated order status to: {order.status}")
        
        print(f"\n🎉 Database write/read operations successful!")
        print(f"   Your database connection is fully functional!")
        
        return True
        
    except Exception as e:
        print(f"❌ Order test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing order database operations...")
    test_simple_order()