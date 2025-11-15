import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from django.db import DatabaseError, IntegrityError
from django.core.cache import cache
from asgiref.sync import sync_to_async
from apps.menu_cache.services import MenuCacheService
from apps.menu_cache.models import MenuCache

@pytest.mark.django_db
class TestMenuCacheErrorHandling:
    """Error handling tests for Menu Cache"""
    
    @pytest.mark.asyncio
    async def test_sync_menu_database_error(self, test_restaurant):
        """Test menu sync when database error occurs"""
        service = MenuCacheService()
        
        with patch('apps.core.services.supabase_client.supabase_client.get_menu', 
                  new_callable=AsyncMock) as mock_get_menu:
            mock_get_menu.return_value = {"categories": []}
            
            with patch('apps.menu_cache.models.MenuCache.objects.filter') as mock_filter:
                mock_filter.side_effect = DatabaseError("Database connection failed")
                
                result = await service.sync_menu_from_supabase(str(test_restaurant.id))
        
        assert result is False
    
    def test_get_cached_menu_cache_error(self, menu_cache):
        """Test get_cached_menu when cache system fails"""
        service = MenuCacheService()
        
        # Mock cache.get to raise exception, but the service should handle it gracefully
        with patch('django.core.cache.cache.get', side_effect=Exception("Redis connection failed")):
            # The service should fall back to database without crashing
            result = service.get_cached_menu(str(menu_cache.restaurant.id))
            
            # Since the database has the menu_cache, it should return the menu_data
            assert result == menu_cache.menu_data
    
    def test_get_cached_menu_database_error(self, test_restaurant):
        """Test get_cached_menu when database fails"""
        service = MenuCacheService()
        
        # Mock cache to return None (cache miss)
        with patch('django.core.cache.cache.get', return_value=None):
            # Mock database query to raise error
            with patch('apps.menu_cache.models.MenuCache.objects.filter') as mock_filter:
                mock_filter.side_effect = DatabaseError("Database connection failed")
                
                # Should return None without crashing
                result = service.get_cached_menu(str(test_restaurant.id))
                assert result is None
    
    def test_calculate_checksum_corrupt_data(self):
        """Test checksum calculation with corrupt data"""
        service = MenuCacheService()
        
        # Data with circular reference (should fail serialization)
        class CircularRef:
            def __init__(self):
                self.ref = self
        
        corrupt_data = {'circular': CircularRef()}
        
        checksum = service.calculate_checksum(corrupt_data)
        assert checksum == ""  # Should return empty string on error
    
    @pytest.mark.asyncio
    async def test_sync_menu_checksum_calculation_error(self, test_restaurant):
        """Test menu sync when checksum calculation fails"""
        service = MenuCacheService()
        
        with patch('apps.core.services.supabase_client.supabase_client.get_menu', 
                  new_callable=AsyncMock) as mock_get_menu:
            mock_get_menu.return_value = {"categories": []}
            
            with patch.object(service, 'calculate_checksum') as mock_checksum:
                mock_checksum.return_value = ""  # Simulate checksum failure
                
                result = await service.sync_menu_from_supabase(str(test_restaurant.id))
        
        assert result is False
    
    def test_invalidate_cache_error(self, test_restaurant):
        """Test cache invalidation when cache system fails"""
        service = MenuCacheService()
        
        # Mock cache.delete to raise exception
        with patch('django.core.cache.cache.delete', side_effect=Exception("Cache deletion failed")):
            # This should not raise an exception - the service should handle it
            try:
                service.invalidate_cache(str(test_restaurant.id))
                # If we get here, the service handled the error
                assert True
            except Exception as e:
                # If the service doesn't handle the error, we need to fix the service
                pytest.fail(f"Service should handle cache errors gracefully, but got: {e}")
    
    def test_menu_cache_integrity_error(self, test_restaurant, sample_menu_data):
        """Test handling of database integrity errors"""
        # Create first menu cache
        MenuCache.objects.create(
            restaurant=test_restaurant,
            menu_data=sample_menu_data,
            version=1,
            is_active=True
        )
        
        # Try to create duplicate (should raise IntegrityError)
        with pytest.raises(IntegrityError):
            MenuCache.objects.create(
                restaurant=test_restaurant,
                menu_data=sample_menu_data,
                version=1,  # Same version - should violate unique constraint
                is_active=True
            )
    
    @pytest.mark.asyncio
    async def test_sync_menu_transaction_rollback(self, test_restaurant):
        """Test that transaction rollback works correctly"""
        service = MenuCacheService()
        
        with patch('apps.core.services.supabase_client.supabase_client.get_menu', 
                  new_callable=AsyncMock) as mock_get_menu:
            mock_get_menu.return_value = {"categories": []}
            
            # Simulate error during transaction
            with patch('apps.menu_cache.models.MenuCache.objects.create') as mock_create:
                mock_create.side_effect = DatabaseError("Create failed")
                
                result = await service.sync_menu_from_supabase(str(test_restaurant.id))
        
        assert result is False
        
        # Verify no active cache was created - use sync_to_async for the query
        active_caches_count = await sync_to_async(
            lambda: MenuCache.objects.filter(restaurant=test_restaurant, is_active=True).count()
        )()
        assert active_caches_count == 0