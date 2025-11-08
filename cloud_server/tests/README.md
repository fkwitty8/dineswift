# DineSwift Testing Suite

## Test Structure

```
tests/
├── __init__.py
├── test_order_storage.py         # Order management tests
├── test_user_management.py       # User and role tests  
├── test_menu_management.py       # Menu and item tests
├── test_inventory_management.py  # Inventory tests
├── test_payment_processing.py    # Payment tests
├── test_table_management.py      # Table and booking tests
├── test_database_connection.py   # Database connectivity tests
├── test_production_database.py   # Production DB tests
├── check_db_connection.py        # DB connection script
├── test_order_insert.py          # Order insertion test
├── test_complete_order.py        # Complete order test
├── test_order_simple.py          # Simple order test
├── database_test_results.md      # DB test results
├── test_database_summary.md      # DB summary
└── README.md                     # This file
```

## Requirements Tested

✅ **Order Storage** - Sales orders, supply orders, order items
✅ **User Management** - User creation, role assignment  
✅ **Menu Management** - Menu items, ingredients
✅ **Inventory Management** - Stock tracking, low stock alerts
✅ **Payment Processing** - Payment creation, status updates
✅ **Table Management** - Table creation, bookings
✅ **Database Connection** - PostgreSQL connectivity and operations

## Running Tests

```bash
# Run all pytest tests
export DJANGO_SETTINGS_MODULE=cloud_server.test_settings && pytest tests/ -v

# Run specific test file
export DJANGO_SETTINGS_MODULE=cloud_server.test_settings && pytest tests/test_order_storage.py -v

# Run with coverage
export DJANGO_SETTINGS_MODULE=cloud_server.test_settings && pytest tests/ --cov=cloud_api --cov-report=term-missing

# Run database connection test
python tests/check_db_connection.py

# Run order insertion tests
python tests/test_order_simple.py
```

## Test Results
- 14 pytest tests passing
- 100% model coverage for tested requirements
- Database connection fully functional
- Order insertion/retrieval working