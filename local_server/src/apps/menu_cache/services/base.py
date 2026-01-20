"""
Base Service Class with Common Functionality
"""
import logging
import hashlib
import json
import uuid
from typing import Dict, Optional, Any
from abc import ABC, abstractmethod
from django.core.cache import cache
from django.utils import timezone

from apps.core.models import ActivityLog, Restaurant
from apps.core.services.supabase_client import supabase_client
from apps.menu_cache.models import MenuCache

logger = logging.getLogger('dineswift')

class BaseMenuService(ABC):
    """
    Abstract base class for menu caching operations
    UC-BASE-001: Common menu operations
    """
    
    def __init__(self):
        self.cache_timeout = 3600  # 1 hour
        self.cache_prefix = "menu"
    
    @abstractmethod
    def get_cached_menu(self, restaurant_id: str) -> Optional[Dict]:
        """Get menu from cache with fallback strategy"""
        pass
    
    def calculate_checksum(self, menu_data: Dict) -> str:
        """Calculate SHA-256 checksum for menu data integrity"""
        try:
            menu_string = json.dumps(menu_data, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(menu_string.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Checksum calculation failed: {str(e)}")
            return ""
    
    def invalidate_cache(self, restaurant_id: str) -> bool:
        """Invalidate cache for a restaurant"""
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        try:
            cache.delete(cache_key)
            logger.info(f"Menu cache invalidated for restaurant {restaurant_id}")
            return True
        except Exception as e:
            logger.warning(f"Cache invalidation error: {str(e)}")
            return False
    
    def get_menu_version(self, restaurant_id: str) -> Optional[Dict]:
        """Get current menu version info"""
        try:
            restaurant_uuid = uuid.UUID(restaurant_id)
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_uuid,
                is_active=True
            ).first()
            
            if menu_cache:
                return {
                    'version': menu_cache.version,
                    'checksum': menu_cache.checksum,
                    'last_synced': menu_cache.last_synced,
                    'restaurant_id': restaurant_id
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get menu version: {str(e)}")
            return None
    
    def _save_menu_to_db(self, restaurant_id: str, menu_data: Dict) -> bool:
        """Save menu to database (common implementation)"""
        try:
            restaurant_uuid = uuid.UUID(restaurant_id)
            restaurant = Restaurant.objects.filter(id=restaurant_uuid).first()
            
            if not restaurant:
                logger.error(f"Restaurant not found: {restaurant_id}")
                return False
            
            # Calculate checksum
            checksum = self.calculate_checksum(menu_data)
            
            # Get or create menu cache
            menu_cache, created = MenuCache.objects.update_or_create(
                restaurant=restaurant,
                is_active=True,
                defaults={
                    'menu_data': menu_data,
                    'checksum': checksum,
                    'last_synced': timezone.now()
                }
            )
            
            # Increment version if not created
            if not created:
                menu_cache.version += 1
                menu_cache.save()
            
            # Update cache
            cache_key = f"{self.cache_prefix}_{restaurant_id}"
            cache.set(cache_key, menu_data, self.cache_timeout)
            
            logger.info(f"Menu saved to cache for restaurant {restaurant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save menu to DB: {str(e)}")
            return False
    
    def _get_restaurant(self, restaurant_id: str) -> Optional[Restaurant]:
        """Get restaurant by ID (common helper)"""
        try:
            restaurant_uuid = uuid.UUID(restaurant_id)
            return Restaurant.objects.filter(id=restaurant_uuid).first()
        except ValueError as e:
            logger.error(f"Invalid restaurant ID format: {restaurant_id}")
            return None