#!/usr/bin/env python
import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')
django.setup()

from cloud_api.models import Restaurant, Order

def test_order_insert():
    """Test inserting an order into the database"""
    try:
        # Create a restaurant first
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St', 'city': 'Test City'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        print(f"✅ Created restaurant: {restaurant.name} (ID: {restaurant.id})")
        
        # Create an order
        order = Order.objects.create(
            restaurant=restaurant,
            order_type='sales',
            status='pending',
            total_amount=Decimal('25.99'),
            notes='Test order for database access'
        )
        print(f"✅ Created order: {order.id}")
        print(f"   Type: {order.order_type}")
        print(f"   Status: {order.status}")
        print(f"   Amount: ${order.total_amount}")
        print(f"   Created: {order.created_at}")
        
        # Verify by querying back
        retrieved_order = Order.objects.get(id=order.id)
        print(f"✅ Retrieved order: {retrieved_order.id}")
        
        # Clean up
        order.delete()
        restaurant.delete()
        print("✅ Cleanup completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Order insert failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing order insertion...")
    test_order_insert()