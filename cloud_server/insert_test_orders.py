#!/usr/bin/env python3
import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')
django.setup()

from cloud_api.models import Order, Restaurant
from decimal import Decimal

def insert_test_orders():
    try:
        # Create test restaurant
        restaurant, created = Restaurant.objects.get_or_create(
            name='Test Restaurant',
            defaults={
                'description': 'Test restaurant for orders',
                'address': {'street': '123 Test St', 'city': 'Test City'},
                'contact_info': {'phone': '123456789'},
                'operation_hours': {'open': '09:00', 'close': '22:00'}
            }
        )
        
        # Create 10 test orders
        orders_created = 0
        for i in range(1, 11):
            order = Order.objects.create(
                restaurant=restaurant,
                order_type='sales',
                status='pending',
                total_amount=Decimal(f'{15000 + (i * 5000)}'),
                notes=f'Test order {i}'
            )
            orders_created += 1
            print(f'Created order {i}: {str(order.id)[:8]}...')
        
        print(f'✅ Successfully created {orders_created} orders')
        print(f'📊 Total orders in database: {Order.objects.count()}')
        
    except Exception as e:
        print(f'❌ Error: {e}')
        print('💡 Make sure database connection is available')

if __name__ == '__main__':
    insert_test_orders()