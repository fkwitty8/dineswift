#!/usr/bin/env python
import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')
django.setup()

from django.db import connection

def test_database_connection():
    """Simple database connection test"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print("✅ Database connection successful!")
            print(f"   Test query result: {result[0]}")
            
            # Get database info
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"   Database: {version.split(',')[0]}")
            
            # Check if tables exist
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_count = cursor.fetchone()[0]
            print(f"   Tables in database: {table_count}")
            
            return True
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing database connection...")
    test_database_connection()