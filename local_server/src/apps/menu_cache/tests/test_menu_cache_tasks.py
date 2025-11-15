import pytest
from unittest.mock import patch, MagicMock
from apps.menu_cache.tasks import sync_all_restaurant_menus, sync_single_restaurant_menu
import uuid

@pytest.mark.django_db
class TestMenuCacheTasks:
    """Unit tests for Menu Cache Celery tasks"""
    
    @patch('apps.menu_cache.tasks.MenuCacheService')
    def test_sync_all_restaurant_menus_success(self, mock_service_class, test_restaurant):
        """Test successful sync of all restaurant menus"""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.sync_menu_from_supabase.return_value = True
        
        # Create multiple restaurants
        from apps.core.models import Restaurant
        restaurant2 = Restaurant.objects.create(
            supabase_restaurant_id=str(uuid.uuid4()),
            name='Test Restaurant 2',
            is_active=True
        )
        
        result = sync_all_restaurant_menus()
        
        assert result['synced'] == 2
        assert result['failed'] == 0
        assert mock_service.sync_menu_from_supabase.call_count == 2
    
    @patch('apps.menu_cache.tasks.MenuCacheService')
    def test_sync_all_restaurant_menus_partial_failure(self, mock_service_class, test_restaurant):
        """Test sync with partial failures"""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.sync_menu_from_supabase.side_effect = [True, False]
        
        # Create multiple restaurants
        from apps.core.models import Restaurant
        restaurant2 = Restaurant.objects.create(
            supabase_restaurant_id=str(uuid.uuid4()),
            name='Test Restaurant 2',
            is_active=True
        )
        
        result = sync_all_restaurant_menus()
        
        assert result['synced'] == 1
        assert result['failed'] == 1
    
    @patch('apps.menu_cache.tasks.MenuCacheService')
    def test_sync_all_restaurant_menus_exception(self, mock_service_class):
        """Test sync when exception occurs"""
        mock_service_class.side_effect = Exception("Service initialization failed")
        
        result = sync_all_restaurant_menus()
        
        assert 'error' in result
        assert 'Service initialization failed' in result['error']
    
    @patch('apps.menu_cache.tasks.MenuCacheService')
    def test_sync_single_restaurant_menu_success(self, mock_service_class, test_restaurant):
        """Test successful sync of single restaurant menu"""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.sync_menu_from_supabase.return_value = True
        
        result = sync_single_restaurant_menu(str(test_restaurant.id))
        
        assert result['success'] is True
        assert result['restaurant_id'] == str(test_restaurant.id)
        mock_service.sync_menu_from_supabase.assert_called_once_with(str(test_restaurant.id))
    
    @patch('apps.menu_cache.tasks.MenuCacheService')
    def test_sync_single_restaurant_menu_failure(self, mock_service_class, test_restaurant):
        """Test failed sync of single restaurant menu"""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.sync_menu_from_supabase.return_value = False
        
        result = sync_single_restaurant_menu(str(test_restaurant.id))
        
        assert result['success'] is False
        assert result['restaurant_id'] == str(test_restaurant.id)
    
    @patch('apps.menu_cache.tasks.MenuCacheService')
    def test_sync_single_restaurant_menu_exception(self, mock_service_class, test_restaurant):
        """Test sync when exception occurs"""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.sync_menu_from_supabase.side_effect = Exception("Sync failed")
        
        result = sync_single_restaurant_menu(str(test_restaurant.id))
        
        assert result['success'] is False
        assert 'error' in result
        assert 'Sync failed' in result['error']