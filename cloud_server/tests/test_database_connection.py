import pytest
from django.db import connection
from django.core.management.color import no_style
from django.db.utils import ConnectionHandler
from cloud_api.models import User, Restaurant


@pytest.mark.django_db
class TestDatabaseConnection:
    
    def test_database_connection(self):
        """Test basic database connectivity"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1
    
    def test_database_tables_exist(self):
        """Test that required tables exist"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            """)
            result = cursor.fetchone()
            assert result is not None
    
    def test_create_and_query_user(self):
        """Test creating and querying a user"""
        user = User.objects.create_user(
            username='dbtest',
            email='dbtest@example.com'
        )
        
        # Query the user back
        retrieved_user = User.objects.get(username='dbtest')
        assert retrieved_user.email == 'dbtest@example.com'
    
    def test_database_settings(self):
        """Test database configuration"""
        from django.conf import settings
        db_config = settings.DATABASES['default']
        
        assert db_config['ENGINE'] == 'django.db.backends.postgresql'
        assert 'NAME' in db_config
        assert 'HOST' in db_config