#!/usr/bin/env python
"""
Test script for the add menu item API
"""
import requests
import json

# API endpoint
BASE_URL = "http://localhost:8000"
ADD_MENU_ITEM_URL = f"{BASE_URL}/api/menu/items/add/"

# Sample data for adding a menu item
sample_menu_item = {
    "menu": "your-menu-uuid-here",  # Replace with actual menu UUID
    "item_name": "Grilled Chicken Sandwich",
    "description": "Juicy grilled chicken breast with fresh vegetables and special sauce",
    "sales_price": "12.99",
    "preparation_time": 15,
    "department": "Kitchen",
    "is_available": True,
    "display_order": 1
}

def test_add_menu_item():
    """Test adding a menu item"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer your-auth-token-here'  # Replace with actual token
    }
    
    response = requests.post(
        ADD_MENU_ITEM_URL,
        headers=headers,
        data=json.dumps(sample_menu_item)
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    print("Testing Add Menu Item API...")
    test_add_menu_item()