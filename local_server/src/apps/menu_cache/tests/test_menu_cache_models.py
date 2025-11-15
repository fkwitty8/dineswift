import pytest
from django.db import IntegrityError
from apps.menu_cache.models import MenuCache

@pytest.mark.django_db
class TestMenuCacheModels:
    """Unit tests for MenuCache model"""
    
    def test_menu_cache_creation(self, test_restaurant, sample_menu_data):
        """Test creating MenuCache with all fields"""
        menu_cache = MenuCache.objects.create(
            restaurant=test_restaurant,
            menu_data=sample_menu_data,
            version=1,
            is_active=True
        )
        
        assert menu_cache.restaurant == test_restaurant
        assert menu_cache.menu_data == sample_menu_data
        assert menu_cache.version == 1
        assert menu_cache.is_active is True
        assert menu_cache.checksum is not None
        assert str(menu_cache) == f"Menu v1 - {test_restaurant.name}"
    
    def test_checksum_calculation(self, test_restaurant, sample_menu_data):
        """Test checksum calculation for data integrity"""
        # Create initial menu cache
        menu_cache = MenuCache.objects.create(
            restaurant=test_restaurant,
            menu_data=sample_menu_data,
            version=1
        )
        
        # Checksum should be automatically calculated
        assert menu_cache.checksum is not None
        assert len(menu_cache.checksum) == 64  # SHA-256 length
        original_checksum = menu_cache.checksum
        
        # Same data should produce same checksum on save
        menu_cache.save()
        assert menu_cache.checksum == original_checksum
        
        # Different data should produce different checksum when updated
        modified_data = sample_menu_data.copy()
        modified_data['categories'][0]['items'][0]['price'] = "6.99"
        
        # Update the existing instance - checksum should change
        menu_cache.menu_data = modified_data
        menu_cache.save()
        
        # This is the key assertion - checksum MUST change when data changes
        assert menu_cache.checksum != original_checksum
        assert menu_cache.checksum == menu_cache.calculate_checksum()    
        
    def test_unique_together_constraint(self, test_restaurant, sample_menu_data):
        """Test unique together constraint for restaurant and version"""
        MenuCache.objects.create(
            restaurant=test_restaurant,
            menu_data=sample_menu_data,
            version=1
        )
        
        # Creating another with same restaurant and version should fail
        with pytest.raises(IntegrityError):
            MenuCache.objects.create(
                restaurant=test_restaurant,
                menu_data=sample_menu_data,
                version=1
            )
    
    def test_model_indexes(self, test_restaurant, sample_menu_data):
        """Test that model indexes work correctly"""
        # Create multiple menu caches
        for i in range(3):
            MenuCache.objects.create(
                restaurant=test_restaurant,
                menu_data=sample_menu_data,
                version=i + 1,
                is_active=(i == 0)  # Only first is active
            )
        
        # Test queries that should use indexes
        active_menus = MenuCache.objects.filter(
            restaurant=test_restaurant,
            is_active=True
        )
        assert active_menus.count() == 1
        
        # Test checksum index
        menu_cache = MenuCache.objects.filter(
            restaurant=test_restaurant,
            is_active=True
        ).first()
        
        same_checksum_menus = MenuCache.objects.filter(checksum=menu_cache.checksum)
        assert same_checksum_menus.count() >= 1
    
    def test_menu_cache_str_representation(self, menu_cache):
        """Test string representation of MenuCache"""
        expected_str = f"Menu v{menu_cache.version} - {menu_cache.restaurant.name}"
        assert str(menu_cache) == expected_str
    
    def test_menu_cache_meta_options(self, menu_cache):
        """Test model Meta options"""
        assert menu_cache._meta.db_table == 'menu_cache'
        
        # Django stores unique_together as tuple of tuples
        assert menu_cache._meta.unique_together == (('restaurant', 'version'),)
        
        # Check indexes - convert to comparable format
        index_fields = [tuple(idx.fields) for idx in menu_cache._meta.indexes]
        assert ('restaurant', 'is_active') in index_fields
        assert ('checksum',) in index_fields