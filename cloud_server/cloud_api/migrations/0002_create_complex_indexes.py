from django.db import migrations
from django.contrib.postgres.operations import CreateExtension

class Migration(migrations.Migration):

    dependencies = [
        ('cloud_api', '0001_initial'),
    ]

    operations = [
        # Enable PostgreSQL extensions
        CreateExtension('uuid-ossp'),
        CreateExtension('pg_trgm'),
        CreateExtension('btree_gin'),

        # Enable the btree_gist extension
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS btree_gist;",
            reverse_sql="DROP EXTENSION IF EXISTS btree_gist;"
        ),
        
        # Restaurant JSONB expression indexes
        migrations.RunSQL(
            """
            -- Restaurant address and operation hours indexes
            CREATE INDEX idx_restaurants_address_city ON restaurants USING gin ((address->>'city'));
            CREATE INDEX idx_restaurants_operation_hours ON restaurants USING gin (operation_hours);
            
            -- Restaurant geo index (if coordinates exist in address)
            CREATE INDEX idx_restaurants_geo ON restaurants USING gist (
                ( (address->'coordinates'->>'lat')::float ),
                ( (address->'coordinates'->>'lng')::float )
            );
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_restaurants_address_city;
            DROP INDEX IF EXISTS idx_restaurants_operation_hours;
            DROP INDEX IF EXISTS idx_restaurants_geo;
            """
        ),
        
        # Menu Items full-text search indexes
        migrations.RunSQL(
            """
            CREATE INDEX idx_menu_items_name_search ON menu_items USING gin (item_name gin_trgm_ops);
            CREATE INDEX idx_inventory_name_search ON inventory_items USING gin (item_name gin_trgm_ops);
            CREATE INDEX idx_suppliers_company_name ON suppliers USING gin (company_name gin_trgm_ops);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_menu_items_name_search;
            DROP INDEX IF EXISTS idx_inventory_name_search;
            DROP INDEX IF EXISTS idx_suppliers_company_name;
            """
        ),
        
        # JSONB field indexes
        migrations.RunSQL(
            """
            CREATE INDEX idx_suppliers_contact_info ON suppliers USING gin (contact_info);
            CREATE INDEX idx_users_communication_prefs ON users USING gin (communication_preferences);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_suppliers_contact_info;
            DROP INDEX IF EXISTS idx_users_communication_prefs;
            """
        ),
    ]