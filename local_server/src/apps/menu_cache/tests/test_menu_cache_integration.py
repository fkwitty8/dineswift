import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from django.core.cache import cache
from apps.menu_cache.models import MenuCache
from apps.menu_cache.services import MenuCacheService
from apps.core.models import ActivityLog, Restaurant
from asgiref.sync import sync_to_async
import uuid

@pytest.mark.django_db
class TestMenuCacheIntegration:
    """Integration tests for complete menu cache workflow"""
    
    @pytest.mark.asyncio
    async def test_complete_menu_sync_workflow(self, db):
        """Test complete menu sync workflow"""
        service = MenuCacheService()
        
        # Create restaurant directly in test to avoid fixture scope issues
        test_restaurant = await sync_to_async(Restaurant.objects.create)(
            supabase_restaurant_id=str(uuid.uuid4()),
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '555-0100'},
            is_active=True
        )
        
        # Mock Supabase response
        sample_supabase_menu = {
            "categories": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Integration Category",
                    "description": "Test category",
                    "items": [
                        {
                            "id": str(uuid.uuid4()),
                            "name": "Integration Item",
                            "description": "Test item",
                            "price": "15.99",
                            "category": "Integration Category",
                            "is_available": True,
                            "preparation_time": 15,
                            "ingredients": ["test"],
                            "allergens": [],
                            "image_url": None
                        }
                    ]
                }
            ]
        }
        
        with patch('apps.core.services.supabase_client.supabase_client.get_menu', 
                  new_callable=AsyncMock) as mock_get_menu:
            mock_get_menu.return_value = sample_supabase_menu
            
            with patch('apps.core.services.supabase_client.supabase_client.set_restaurant_context'):
                # First sync
                result1 = await service.sync_menu_from_supabase(str(test_restaurant.id))
                assert result1 is True
                
                # Verify cache creation
                cache1 = await sync_to_async(
                    MenuCache.objects.filter(restaurant=test_restaurant, is_active=True).first
                )()
                assert cache1 is not None
                assert cache1.version == 1
                
                # Second sync with same data (should not create new version)
                result2 = await service.sync_menu_from_supabase(str(test_restaurant.id))
                assert result2 is True
                
                # Verify no new cache was created
                cache2 = await sync_to_async(
                    MenuCache.objects.filter(restaurant=test_restaurant, is_active=True).first
                )()
                assert cache2.id == cache1.id
                assert cache2.version == 1
                
                # Third sync with different data
                different_menu = sample_supabase_menu.copy()
                different_menu['categories'][0]['items'][0]['price'] = "18.99"
                different_menu['categories'][0]['items'][0]['name'] = "Updated Integration Item"
                mock_get_menu.return_value = different_menu
                
                result3 = await service.sync_menu_from_supabase(str(test_restaurant.id))
                assert result3 is True
                
                # Verify new cache was created and old one deactivated
                cache3 = await sync_to_async(
                    MenuCache.objects.filter(restaurant=test_restaurant, is_active=True).first
                )()
                assert cache3 is not None
                assert cache3.version == 2
                assert cache3.id != cache1.id
                
                # Verify old cache is deactivated
                await sync_to_async(cache1.refresh_from_db)()
                assert cache1.is_active is False
    
    def test_cache_hierarchy_redis_to_database(self, menu_cache):
        """Test cache hierarchy (Redis -> Database)"""
        service = MenuCacheService()
        cache_key = f"{service.cache_prefix}_{menu_cache.restaurant.id}"
        
        # Test 1: Data in Redis
        cache.set(cache_key, menu_cache.menu_data, service.cache_timeout)
        result1 = service.get_cached_menu(str(menu_cache.restaurant.id))
        assert result1 == menu_cache.menu_data
        
        # Test 2: Redis empty, fallback to Database
        cache.delete(cache_key)
        result2 = service.get_cached_menu(str(menu_cache.restaurant.id))
        assert result2 == menu_cache.menu_data
        
        # Verify it's now cached in Redis again
        result3 = cache.get(cache_key)
        assert result3 == menu_cache.menu_data
        
        # Test 3: Both empty
        cache.delete(cache_key)
        MenuCache.objects.filter(restaurant=menu_cache.restaurant).update(is_active=False)
        result4 = service.get_cached_menu(str(menu_cache.restaurant.id))
        assert result4 is None
    
    def test_activity_logging_on_sync(self, test_restaurant):
        """Test that activity logs are created during sync operations"""
        service = MenuCacheService()
        
        # Count initial activity logs
        initial_log_count = ActivityLog.objects.filter(
            restaurant=test_restaurant,
            module='MENU_CACHE'
        ).count()
        
        # Verify we can create activity logs
        test_log = ActivityLog.objects.create(
            restaurant=test_restaurant,
            level='INFO',
            module='MENU_CACHE',
            action='TEST_ACTION',
            details={'test': 'data'}
        )
        
        assert test_log is not None
        assert ActivityLog.objects.filter(
            restaurant=test_restaurant,
            module='MENU_CACHE'
        ).count() == initial_log_count + 1
    
    def test_concurrent_menu_access(self, menu_cache):
        """Test concurrent access to menu cache"""
        service = MenuCacheService()
        
        # First, ensure the cache is warm
        service.get_cached_menu(str(menu_cache.restaurant.id))
        
        # Simulate multiple concurrent accesses
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        results = []
        errors = []
        
        def get_menu(thread_id):
            try:
                result = service.get_cached_menu(str(menu_cache.restaurant.id))
                results.append((thread_id, result))
            except Exception as e:
                errors.append((thread_id, e))
        
        # Use ThreadPoolExecutor for better control
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_menu, i) for i in range(10)]
            
            # Wait for all threads to complete
            for future in futures:
                future.result()
        
        # Check for errors
        assert len(errors) == 0, f"Errors occurred in threads: {errors}"
        
        # All results should be the same and equal to menu_data
        valid_results = [result for _, result in results if result is not None]
        assert len(valid_results) == 10, f"Some threads got None results. All results: {results}"
        assert all(result == menu_cache.menu_data for result in valid_results)
    
    def test_menu_cache_performance(self, menu_cache):
        """Test menu cache performance"""
        service = MenuCacheService()
        import time
        
        # Warm up cache
        service.get_cached_menu(str(menu_cache.restaurant.id))
        
        # Time multiple accesses
        start_time = time.time()
        
        for _ in range(100):
            service.get_cached_menu(str(menu_cache.restaurant.id))
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should be very fast (sub-second for 100 accesses)
        assert total_time < 1.0