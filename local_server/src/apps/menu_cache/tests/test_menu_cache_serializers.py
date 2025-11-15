from apps.menu_cache.serializers import (
    MenuItemSerializer, 
    MenuCategorySerializer, 
    MenuCacheSerializer,
    MenuSyncSerializer
)
from uuid import UUID

class TestMenuCacheSerializers:
    """Unit tests for Menu Cache Serializers"""
    
    def test_menu_item_serializer_valid(self):
        """Test valid menu item serialization"""
        valid_data = {
            'id': '12345678-1234-5678-1234-567812345678',
            'name': 'Test Item',
            'description': 'Test Description',
            'price': '10.99',
            'category': 'Test Category',
            'is_available': True,
            'preparation_time': 15,
            'ingredients': ['ing1', 'ing2'],
            'allergens': ['nuts'],
            'image_url': 'https://example.com/image.jpg'
        }
        serializer = MenuItemSerializer(data=valid_data)
        assert serializer.is_valid()
    
    def test_menu_item_serializer_invalid(self):
        """Test invalid menu item serialization"""
        invalid_data = {
            'id': 'invalid-uuid',  # Invalid UUID
            'name': '',  # Blank name
            'price': '-5.00'  # Negative price
            # Missing required fields: category
        }
        serializer = MenuItemSerializer(data=invalid_data)
        assert not serializer.is_valid()
        # Check for specific errors
        assert 'id' in serializer.errors  # Invalid UUID
        assert 'name' in serializer.errors  # Blank name
        assert 'category' in serializer.errors  # Missing required field
        assert 'price' in serializer.errors  # Negative price
    
    def test_menu_category_serializer_valid(self, sample_menu_data):
        """Test MenuCategorySerializer with valid data"""
        category_data = sample_menu_data['categories'][0]
        serializer = MenuCategorySerializer(data=category_data)
        assert serializer.is_valid()
    
    def test_menu_cache_serializer_output(self, menu_cache):
        """Test MenuCacheSerializer output format"""
        serializer = MenuCacheSerializer(menu_cache)
        data = serializer.data
        
        expected_fields = [
            'id', 'restaurant', 'restaurant_name', 'version', 'checksum',
            'is_active', 'last_synced', 'menu_items_count', 'categories',
            'created_at', 'updated_at'
        ]
        
        for field in expected_fields:
            assert field in data
        
        assert data['restaurant_name'] == menu_cache.restaurant.name
        assert data['menu_items_count'] == 2  # From sample data
        assert len(data['categories']) == 2
    
    def test_menu_cache_serializer_menu_items_count(self, menu_cache):
        """Test menu_items_count calculation"""
        serializer = MenuCacheSerializer(menu_cache)
        assert serializer.get_menu_items_count(menu_cache) == 2
        
        # Test with empty menu data
        menu_cache.menu_data = {}
        assert serializer.get_menu_items_count(menu_cache) == 0
        
        # Test with None menu data
        menu_cache.menu_data = None
        assert serializer.get_menu_items_count(menu_cache) == 0
    
    def test_menu_sync_serializer_validation(self):
        """Test MenuSyncSerializer validation"""
        # Test without restaurant_id (should use context)
        serializer = MenuSyncSerializer(data={'force_refresh': True})
        
        # Mock request context
        class MockUser:
            restaurant_id = 'test-restaurant-id'
        
        class MockRequest:
            user = MockUser()
        
        serializer.context['request'] = MockRequest()
        
        assert serializer.is_valid()
        assert serializer.validated_data['restaurant_id'] == 'test-restaurant-id'
        
        # Test with explicit restaurant_id
        valid_uuid = 'a1b2c3d4-e5f6-7890-1234-567890abcdef'
        explicit_data = {
            'force_refresh': False,
            'restaurant_id': valid_uuid 
        }
        serializer = MenuSyncSerializer(data=explicit_data)
        assert serializer.is_valid()
        
        # 2. Convert the expected value to a UUID object for comparison
        expected_uuid_object = UUID(valid_uuid)
        
        assert serializer.validated_data['restaurant_id'] == expected_uuid_object 