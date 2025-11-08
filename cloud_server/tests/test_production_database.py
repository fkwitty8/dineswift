import pytest
from django.db import connection
from django.test import override_settings
from cloud_api.models import Restaurant


@pytest.mark.django_db
class TestProductionDatabase:
    
    def test_database_connection_basic(self):
        """Test basic database connectivity"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()
            assert result[0] == 1
    
    def test_database_version(self):
        """Test PostgreSQL version"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            result = cursor.fetchone()
            assert 'PostgreSQL' in result[0]
    
    def test_create_restaurant_only(self):
        """Test creating restaurant without user dependencies"""
        restaurant = Restaurant.objects.create(
            name='DB Connection Test',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        
        # Verify creation
        assert restaurant.name == 'DB Connection Test'
        assert restaurant.id is not None
        
        # Clean up
        restaurant.delete()
    
    def test_database_tables_count(self):
        """Test that tables exist"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM pg_tables 
                WHERE schemaname = 'public'
            """)
            result = cursor.fetchone()
            assert result[0] > 0  # Should have tables