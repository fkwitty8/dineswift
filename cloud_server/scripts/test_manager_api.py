#!/usr/bin/env python
import os
import django
import sys

# Add the project directory to Python path
sys.path.append('/home/mushabe/Desktop/dineswift/cloud_server')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')
django.setup()

from cloud_api.models import User, Restaurant, Role, UserRole, Menu, MenuItem

def create_test_data():
    # Create manager role
    manager_role, _ = Role.objects.get_or_create(
        role_name='manager',
        defaults={'permissions': {'menu_management': True}, 'description': 'Restaurant Manager'}
    )
    
    # Create test restaurant
    restaurant, _ = Restaurant.objects.get_or_create(
        name='Test Restaurant',
        defaults={
            'address': {'street': '123 Test St', 'city': 'Test City'},
            'contact_info': {'phone': '123-456-7890'},
            'operation_hours': {'monday': '9:00-22:00'}
        }
    )
    
    # Create manager user
    manager_user, _ = User.objects.get_or_create(
        username='manager1',
        defaults={'email': 'manager@test.com', 'first_name': 'Test', 'last_name': 'Manager'}
    )
    
    # Assign manager role
    UserRole.objects.get_or_create(
        user=manager_user,
        role=manager_role,
        restaurant=restaurant,
        defaults={'is_active': True}
    )
    
    print(f"Created test data:")
    print(f"Restaurant: {restaurant.name} (ID: {restaurant.id})")
    print(f"Manager: {manager_user.username} (ID: {manager_user.id})")
    print(f"Role: {manager_role.role_name} (ID: {manager_role.id})")

if __name__ == '__main__':
    create_test_data()