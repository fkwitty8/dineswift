import pytest
import json
from unittest.mock import patch, MagicMock
from rest_framework import status
from rest_framework.test import APIClient
from django.core.cache import cache
from apps.menu_cache.models import MenuCache

@pytest.mark.django_db
class TestMenuCacheViews:
    
    @patch('apps.menu_cache.services.menu_cache_service.get_cached_menu')
    def test_get_current_menu_success(self, mock_get_cached, authenticated_client, menu_cache):
        """Test successful retrieval of current menu"""
        # Mock the service method to return menu data
        mock_get_cached.return_value = menu_cache.menu_data
        
        response = authenticated_client.get('/api/menu-cache/current/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['restaurant_id'] == menu_cache.restaurant.id
        assert response.data['menu'] == menu_cache.menu_data
        assert response.data['cached'] is True
    
    @patch('apps.menu_cache.services.menu_cache_service.get_cached_menu')
    def test_get_current_menu_not_found(self, mock_get_cached, authenticated_client):
        """Test retrieval when no menu exists"""
        # Mock the service method to return None
        mock_get_cached.return_value = None
        
        response = authenticated_client.get('/api/menu-cache/current/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
    
    def test_get_current_menu_unauthorized(self):
        """Test unauthorized access to current menu"""
        client = APIClient()
        response = client.get('/api/menu-cache/current/')
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @patch('apps.menu_cache.services.menu_cache_service.sync_menu_from_supabase')
    @patch('apps.menu_cache.services.menu_cache_service.get_cached_menu')
    def test_sync_menu_success(self, mock_get_cached, mock_sync, authenticated_client, menu_cache):
        """Test successful menu sync"""
        mock_sync.return_value = True
        mock_get_cached.return_value = menu_cache.menu_data
        
        response = authenticated_client.post('/api/menu-cache/sync/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        assert response.data['message'] == 'Menu synced successfully'
        assert 'menu' in response.data
    
    @patch('apps.menu_cache.services.menu_cache_service.sync_menu_from_supabase')
    def test_sync_menu_failure(self, mock_sync, authenticated_client):
        """Test failed menu sync"""
        # Make absolutely sure the mock returns False
        mock_sync.return_value = False
        
        response = authenticated_client.post('/api/menu-cache/sync/')
        
        # If we're still getting 200, let's check what's happening
        if response.status_code == 200:
            print("Unexpected 200 response - investigating:")
            print(f"Mock called: {mock_sync.called}")
            print(f"Mock return value: {mock_sync.return_value}")
            print(f"Response data: {response.data}")
            
            # Let's see if there's an exception being caught
            import traceback
            traceback.print_stack()
        
        # Force the assertions
        assert mock_sync.called, "Service method was not mocked properly!"
        assert response.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 but got {response.status_code}. Response: {response.data}"
        assert 'error' in response.data
              
    @patch('apps.menu_cache.services.menu_cache_service.get_menu_version')
    def test_get_menu_version_success(self, mock_get_version, authenticated_client, menu_cache):
        """Test successful retrieval of menu version"""
        mock_get_version.return_value = {
            'version': menu_cache.version,
            'checksum': menu_cache.checksum,
            'last_updated': menu_cache.updated_at.isoformat()
        }
        
        response = authenticated_client.get('/api/menu-cache/version/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['version'] == menu_cache.version
        assert response.data['checksum'] == menu_cache.checksum
    
    @patch('apps.menu_cache.services.menu_cache_service.get_menu_version')
    def test_get_menu_version_not_found(self, mock_get_version, authenticated_client):
        """Test retrieval when no menu version exists"""
        mock_get_version.return_value = None
        
        response = authenticated_client.get('/api/menu-cache/version/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
    
    def test_menu_cache_list_success(self, authenticated_client, menu_cache):
        """Test successful menu cache list"""
        response = authenticated_client.get('/api/menu-cache/menus/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(menu_cache.id)
        assert response.data['version'] == menu_cache.version
    
    def test_menu_cache_list_not_found(self, authenticated_client):
        """Test menu cache list when no cache exists"""
        response = authenticated_client.get('/api/menu-cache/menus/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @patch('apps.menu_cache.services.menu_cache_service.sync_menu_from_supabase')
    @patch('apps.menu_cache.services.menu_cache_service.get_cached_menu')
    def test_menu_cache_refresh(self, mock_get_cached, mock_sync, authenticated_client):
        """Test menu cache refresh action"""
        mock_sync.return_value = True
        mock_get_cached.return_value = {'categories': []}
        
        response = authenticated_client.post('/api/menu-cache/menus/refresh/')
        
        assert response.status_code == 200
    
    @patch('apps.menu_cache.services.menu_cache_service.invalidate_cache')
    def test_menu_cache_invalidate_success(self, mock_invalidate, authenticated_client, test_restaurant):
        """Test successful menu cache invalidation"""
        response = authenticated_client.post('/api/menu-cache/menus/invalidate/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'
        mock_invalidate.assert_called_once_with(test_restaurant.id)
    
    @patch('apps.menu_cache.services.menu_cache_service.invalidate_cache')
    def test_menu_cache_invalidate_failure(self, mock_invalidate, authenticated_client):
        """Test menu cache invalidation failure"""
        mock_invalidate.side_effect = Exception("Invalidation failed")
        
        response = authenticated_client.post('/api/menu-cache/menus/invalidate/')
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'error' in response.data