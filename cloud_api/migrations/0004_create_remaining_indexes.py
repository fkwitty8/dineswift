from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('cloud_api', '0003_booking_deliverybatch_kitchendisplayorder_order_and_more'),
    ]

    operations = [
        # Delivery and kitchen optimization indexes (NEW - not in 0002)
        migrations.RunSQL(
            """
            -- Delivery batch optimization indexes
            CREATE INDEX IF NOT EXISTS idx_delivery_batches_restaurant_status ON delivery_batches (restaurant_id, batch_status);
            CREATE INDEX IF NOT EXISTS idx_delivery_batches_waiter_status ON delivery_batches (assigned_waiter_id, batch_status);
            
            -- Kitchen display optimization indexes
            CREATE INDEX IF NOT EXISTS idx_kitchen_orders_order_status ON kitchen_display_orders (order_id, status);
            CREATE INDEX IF NOT EXISTS idx_kitchen_orders_station_status ON kitchen_display_orders (station_assigned, status) WHERE station_assigned IS NOT NULL;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_delivery_batches_restaurant_status;
            DROP INDEX IF EXISTS idx_delivery_batches_waiter_status;
            DROP INDEX IF EXISTS idx_kitchen_orders_order_status;
            DROP INDEX IF EXISTS idx_kitchen_orders_station_status;
            """
        ),

        # Order and sales optimization indexes (NEW - not in 0002)
        migrations.RunSQL(
            """
            -- Order optimization indexes
            CREATE INDEX IF NOT EXISTS idx_orders_restaurant_type_status ON "order" (restaurant_id, order_type, status);
            CREATE INDEX IF NOT EXISTS idx_orders_total_amount ON "order" (total_amount) WHERE total_amount > 100;
            
            -- Sales order optimization indexes
            CREATE INDEX IF NOT EXISTS idx_sales_orders_waiter_status ON sales_orders (assigned_waiter_id, order_id) WHERE assigned_waiter_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_sales_orders_table_status ON sales_orders (table_id, order_id) WHERE table_id IS NOT NULL;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_orders_restaurant_type_status;
            DROP INDEX IF EXISTS idx_orders_total_amount;
            DROP INDEX IF EXISTS idx_sales_orders_waiter_status;
            DROP INDEX IF EXISTS idx_sales_orders_table_status;
            """
        ),

        # Booking optimization indexes (NEW - not in 0002)
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS idx_bookings_date_status ON bookings (booking_date, status);
            CREATE INDEX IF NOT EXISTS idx_bookings_party_size ON bookings (party_size) WHERE party_size > 4;
            CREATE INDEX IF NOT EXISTS idx_bookings_deposit_status ON bookings (deposit_status) WHERE deposit_status = 'paid';
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_bookings_date_status;
            DROP INDEX IF EXISTS idx_bookings_party_size;
            DROP INDEX IF EXISTS idx_bookings_deposit_status;
            """
        ),

        # Inventory and supplier optimization indexes (NEW - not in 0002)
        migrations.RunSQL(
            """
            -- Inventory optimization indexes
            CREATE INDEX IF NOT EXISTS idx_inventory_restaurant_stock ON inventory_items (restaurant_id, stock_status, current_stock);
            CREATE INDEX IF NOT EXISTS idx_inventory_cost_price ON inventory_items (cost_price) WHERE cost_price > 0;
            
            -- Supplier optimization indexes
            CREATE INDEX IF NOT EXISTS idx_suppliers_rating_active ON suppliers (rating, is_active) WHERE is_active = true;
            CREATE INDEX IF NOT EXISTS idx_restaurant_suppliers_active ON restaurant_suppliers (restaurant_id, relationship_status) WHERE relationship_status = 'active';
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_inventory_restaurant_stock;
            DROP INDEX IF EXISTS idx_inventory_cost_price;
            DROP INDEX IF EXISTS idx_suppliers_rating_active;
            DROP INDEX IF EXISTS idx_restaurant_suppliers_active;
            """
        ),

        # User and role optimization indexes (NEW - not in 0002)
        migrations.RunSQL(
            """
            -- User optimization indexes
            CREATE INDEX IF NOT EXISTS idx_users_phone ON users (phone_number) WHERE phone_number IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_users_active_recent ON users (is_active, last_login) WHERE is_active = true;
            
            -- User role optimization indexes
            CREATE INDEX IF NOT EXISTS idx_user_roles_user_active ON user_roles (user_id, is_active) WHERE is_active = true;
            CREATE INDEX IF NOT EXISTS idx_user_roles_restaurant_active ON user_roles (restaurant_id, is_active) WHERE is_active = true AND restaurant_id IS NOT NULL;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_users_phone;
            DROP INDEX IF EXISTS idx_users_active_recent;
            DROP INDEX IF EXISTS idx_user_roles_user_active;
            DROP INDEX IF EXISTS idx_user_roles_restaurant_active;
            """
        ),

        # Performance optimization indexes for common queries (NEW - not in 0002)
        migrations.RunSQL(
            """
            -- Menu performance optimization
            CREATE INDEX IF NOT EXISTS idx_menu_items_active_optimized ON menu_items (menu_id, display_order) WHERE is_available = true;
            
            -- Order items performance optimization
            CREATE INDEX IF NOT EXISTS idx_order_items_price_range ON order_items (unit_price) WHERE unit_price > 50;
            
            -- Restaurant table performance optimization
            CREATE INDEX IF NOT EXISTS idx_tables_capacity_status ON restaurant_tables (capacity, table_status) WHERE table_status = 'available';
            
            -- Local server performance optimization
            CREATE INDEX IF NOT EXISTS idx_local_servers_online ON local_servers (status, last_sync) WHERE status = 'online';
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_menu_items_active_optimized;
            DROP INDEX IF EXISTS idx_order_items_price_range;
            DROP INDEX IF EXISTS idx_tables_capacity_status;
            DROP INDEX IF EXISTS idx_local_servers_online;
            """
        ),

        # Additional composite indexes for better query performance (NEW - not in 0002)
        migrations.RunSQL(
            """
            -- Composite indexes for order filtering
            CREATE INDEX IF NOT EXISTS idx_orders_restaurant_date_type ON "order" (restaurant_id, created_at, order_type);
            CREATE INDEX IF NOT EXISTS idx_orders_status_date_amount ON "order" (status, created_at, total_amount);
            
            -- Composite indexes for menu item searches
            CREATE INDEX IF NOT EXISTS idx_menu_items_search_composite ON menu_items (menu_id, is_available, department, sales_price);
            
            -- Composite indexes for booking management
            CREATE INDEX IF NOT EXISTS idx_bookings_restaurant_customer_date ON bookings (restaurant_id, customer_user_id, booking_date);
            CREATE INDEX IF NOT EXISTS idx_bookings_table_date_status ON bookings (table_id, booking_date, status);
            
            -- Composite indexes for delivery management
            CREATE INDEX IF NOT EXISTS idx_delivery_batches_composite ON delivery_batches (restaurant_id, batch_status, created_at, assigned_waiter_id);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_orders_restaurant_date_type;
            DROP INDEX IF EXISTS idx_orders_status_date_amount;
            DROP INDEX IF EXISTS idx_menu_items_search_composite;
            DROP INDEX IF EXISTS idx_bookings_restaurant_customer_date;
            DROP INDEX IF EXISTS idx_bookings_table_date_status;
            DROP INDEX IF EXISTS idx_delivery_batches_composite;
            """
        ),
    ]