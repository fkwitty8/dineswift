import pytest
import uuid
from decimal import Decimal
from unittest.mock import patch, AsyncMock, Mock
from django.core.cache import cache
from asgiref.sync import sync_to_async

from apps.menu_cache.services import MenuCacheService
from apps.menu_cache.models import MenuCache
from apps.core.models import ActivityLog, Restaurant
from apps.core.services.supabase_client import supabase_client


# HELPER FUNCTION: To create a reliable mock object for asynchronous lookups
def mock_restaurant_with_supabase_id(restaurant_obj):
    """
    Creates a mock restaurant object ensuring the critical supabase_restaurant_id is present.
    """
    mock_res = Mock()
    mock_res.id = restaurant_obj.id if restaurant_obj else str(uuid.uuid4())
    # This critical field must be present for the service to proceed
    mock_res.supabase_restaurant_id = str(uuid.uuid4())
    mock_res.pk = mock_res.id
    return mock_res


@pytest.mark.django_db
class TestMenuCacheServices:
    """Unit tests for MenuCacheService"""
    
    def test_calculate_checksum(self, sample_menu_data):
        """Test checksum calculation"""
        service = MenuCacheService()
        checksum = service.calculate_checksum(sample_menu_data)
        
        assert checksum is not None
        assert len(checksum) == 64
        
        # Same data should produce same checksum
        same_checksum = service.calculate_checksum(sample_menu_data)
        assert checksum == same_checksum
        
        # Different data should produce different checksum
        modified_data = sample_menu_data.copy()
        modified_data['categories'][0]['name'] = 'Different Name'
        different_checksum = service.calculate_checksum(modified_data)
        assert checksum != different_checksum
    
    def test_calculate_checksum_invalid_data(self):
        """Test checksum calculation with invalid data"""
        service = MenuCacheService()
        
        # Test with non-serializable data
        invalid_data = {'decimal_value': Decimal('10.50')}
        checksum = service.calculate_checksum(invalid_data)
        assert checksum == ""
    
    def test_get_cached_menu_redis_hit(self, test_restaurant, sample_menu_data):
        """Test getting menu from Redis cache"""
        service = MenuCacheService()
        cache_key = f"{service.cache_prefix}_{test_restaurant.id}"
        
        # Set cache
        cache.set(cache_key, sample_menu_data, service.cache_timeout)
        
        # Retrieve from cache
        result = service.get_cached_menu(str(test_restaurant.id))
        assert result == sample_menu_data
    
    def test_get_cached_menu_database_fallback(self, menu_cache):
        """Test getting menu from database when Redis cache misses"""
        service = MenuCacheService()
        cache_key = f"{service.cache_prefix}_{menu_cache.restaurant.id}"
        
        # Ensure cache is empty
        cache.delete(cache_key)
        
        # Should fallback to database
        result = service.get_cached_menu(str(menu_cache.restaurant.id))
        assert result == menu_cache.menu_data
        
        # Should now be cached in Redis
        cached_result = cache.get(cache_key)
        assert cached_result == menu_cache.menu_data
    
    def test_get_cached_menu_not_found(self, test_restaurant):
        """Test getting menu when no cache exists"""
        service = MenuCacheService()
        
        result = service.get_cached_menu(str(test_restaurant.id))
        assert result is None
    
    @pytest.mark.asyncio
    async def test_sync_menu_from_supabase_success(self, async_test_restaurant):
        """Test successful menu sync from Supabase"""
        restaurant_obj = await async_test_restaurant
        service = MenuCacheService()
        
        sample_supabase_menu = {
            "categories": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "New Category",
                    "items": [{"id": str(uuid.uuid4()), "name": "New Item", "price": "9.99"}]
                }
            ]
        }
        
        mock_res_instance = mock_restaurant_with_supabase_id(restaurant_obj)
        with patch('apps.menu_cache.services.Restaurant.objects.filter') as mock_res_filter:
            mock_res_filter.return_value.first = lambda: mock_res_instance

            with patch.object(supabase_client, 'set_restaurant_context'):
                with patch.object(supabase_client, 'get_menu', new_callable=AsyncMock) as mock_get_menu:
                    mock_get_menu.return_value = sample_supabase_menu
                    
                    with patch.object(service, 'calculate_checksum') as mock_checksum:
                        mock_checksum.return_value = "test_checksum_123"
                        
                        with patch.object(service, 'invalidate_cache'): # Ensure cache step doesn't fail
                            # Mock the MenuCache lookup inside the service to return None (fresh creation)
                            with patch('apps.menu_cache.services.MenuCache.objects.filter') as mock_cache_filter:
                                mock_cache_filter.return_value.first = lambda: None # No current cache
                                
                                result = await service.sync_menu_from_supabase(str(restaurant_obj.id))
        
        assert result is True
        
        # Verify new cache was created
        new_cache = await sync_to_async(
            MenuCache.objects.filter(
                restaurant=restaurant_obj,
                is_active=True
            ).first
        )()
        assert new_cache is not None
        assert new_cache.menu_data == sample_supabase_menu

    
    @pytest.mark.asyncio
    async def test_sync_menu_from_supabase_no_changes(self, menu_cache):
        """Test menu sync when no changes detected"""
        service = MenuCacheService()
        
        # FIX: Create a stable Mock MenuCache instance using fixture data
        mock_cache_instance = Mock()
        mock_cache_instance.checksum = menu_cache.checksum
        mock_cache_instance.restaurant = menu_cache.restaurant
        mock_cache_instance.menu_data = menu_cache.menu_data
        mock_cache_instance.version = menu_cache.version

        mock_res_instance = mock_restaurant_with_supabase_id(menu_cache.restaurant)
        with patch('apps.menu_cache.services.Restaurant.objects.filter') as mock_res_filter:
            mock_res_filter.return_value.first = lambda: mock_res_instance

            # Patch MenuCache lookup to return the stable MOCK instance
            with patch('apps.menu_cache.services.MenuCache.objects.filter') as mock_cache_filter:
                mock_cache_filter.return_value.first = lambda: mock_cache_instance
        
                # FIX: Patch the MenuCache creation call inside the service
                with patch('apps.menu_cache.services.MenuCache.objects.create') as mock_cache_create:
                    with patch.object(supabase_client, 'set_restaurant_context'):
                        with patch.object(supabase_client, 'get_menu', new_callable=AsyncMock) as mock_get_menu:
                            mock_get_menu.return_value = menu_cache.menu_data
                            
                            with patch.object(service, 'calculate_checksum') as mock_checksum:
                                mock_checksum.return_value = menu_cache.checksum
                                
                                # Patch invalidate_cache to ensure it runs without error
                                with patch.object(service, 'invalidate_cache') as mock_invalidate:
                                    result = await service.sync_menu_from_supabase(str(menu_cache.restaurant.id))
        
        assert result is True
        
        # FINAL FIX: Assert that no new object was created, instead of relying on unstable database lookup
        mock_cache_create.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_sync_menu_from_supabase_restaurant_not_found(self):
        """Test menu sync with non-existent restaurant"""
        service = MenuCacheService()
        
        result = await service.sync_menu_from_supabase('00000000-0000-0000-0000-000000000999')
        assert result is False
    
    @pytest.mark.asyncio
    async def test_sync_menu_from_supabase_supabase_error(self, test_restaurant):
        """Test menu sync when Supabase returns error"""
        restaurant_obj = test_restaurant 
        service = MenuCacheService()

        mock_res_instance = mock_restaurant_with_supabase_id(restaurant_obj)
        with patch('apps.menu_cache.services.Restaurant.objects.filter') as mock_res_filter:
            mock_res_filter.return_value.first = lambda: mock_res_instance
        
            # FIX: Patch ActivityLog creation to assert it was called
            with patch('apps.menu_cache.services.ActivityLog.objects.create') as mock_activity_log_create:
                
                with patch.object(supabase_client, 'set_restaurant_context'):
                    with patch.object(supabase_client, 'get_menu', new_callable=AsyncMock) as mock_get_menu:
                        mock_get_menu.side_effect = Exception("Supabase connection failed")
                        
                        result = await service.sync_menu_from_supabase(str(restaurant_obj.id))
            
            assert result is False
            
            # Assert that the ActivityLog was attempted to be created
            mock_activity_log_create.assert_called_once()
        
    def test_invalidate_cache(self, test_restaurant):
        """Test cache invalidation with mock"""
        service = MenuCacheService()
        cache_key = f"{service.cache_prefix}_{test_restaurant.id}"
        
        with patch.object(cache, 'set') as mock_set, \
            patch.object(cache, 'get') as mock_get, \
            patch.object(cache, 'delete') as mock_delete:
            
            # Mock cache behavior
            mock_get.side_effect = [
                "test_data",
                None
            ]
            
            # Invalidate cache
            service.invalidate_cache(str(test_restaurant.id))
            
            # Verify delete was called with correct key
            mock_delete.assert_called_once_with(cache_key)
    
    def test_get_menu_version(self, menu_cache):
        """Test getting menu version information"""
        service = MenuCacheService()
        
        version_info = service.get_menu_version(str(menu_cache.restaurant.id))
        
        assert version_info is not None
        assert version_info['version'] == menu_cache.version
        assert version_info['checksum'] == menu_cache.checksum
        assert version_info['restaurant_id'] == str(menu_cache.restaurant.id)
    
    def test_get_menu_version_not_found(self, test_restaurant):
        """Test getting menu version when no cache exists"""
        service = MenuCacheService()
        
        version_info = service.get_menu_version(str(test_restaurant.id))
        assert version_info is None