import logging
import hashlib
import json
from typing import Dict, Optional
from django.core.cache import cache
from django.utils import timezone
from apps.core.models import ActivityLog
from apps.core.services.supabase_client import supabase_client
from .models import MenuCache, Restaurant

logger = logging.getLogger('dineswift')

class MenuCacheService:
    """
    Service for managing menu caching operations
    UC-LOCAL-ORDER-101: Cache Menu Data
    """
    
    def __init__(self):
        self.cache_timeout = 3600  # 1 hour
        self.cache_prefix = "menu"
    
    def get_cached_menu(self, restaurant_id: str) -> Optional[Dict]:
        """Get menu from cache with fallback to database"""
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        
        # Try Redis cache first
        cached_menu = cache.get(cache_key)
        if cached_menu:
            logger.debug(f"Menu cache HIT for restaurant {restaurant_id}")
            return cached_menu
        
        # Fallback to database
        try:
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_id,
                is_active=True
            ).first()
            
            if menu_cache:
                # Cache in Redis for future requests
                cache.set(cache_key, menu_cache.menu_data, self.cache_timeout)
                logger.debug(f"Menu loaded from DB for restaurant {restaurant_id}")
                return menu_cache.menu_data
        
        except Exception as e:
            logger.error(f"Failed to get cached menu: {str(e)}", exc_info=True)
        
        logger.warning(f"No menu found for restaurant {restaurant_id}")
        return None
    
    def calculate_checksum(self, menu_data: Dict) -> str:
        """Calculate SHA-256 checksum for menu data integrity"""
        try:
            # Sort keys to ensure consistent hashing
            menu_string = json.dumps(menu_data, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(menu_string.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Checksum calculation failed: {str(e)}")
            return ""
    
    async def sync_menu_from_supabase(self, restaurant_id: str) -> bool:
        """
        UC-LOCAL-ORDER-101: Sync menu from Supabase to local cache
        """
        try:
            # Get restaurant
            restaurant = Restaurant.objects.get(id=restaurant_id)
            
            # Set restaurant context for RLS
            supabase_client.set_restaurant_context(str(restaurant.supabase_restaurant_id))
            
            # Fetch latest menu from Supabase
            supabase_menu = supabase_client.get_menu(str(restaurant.supabase_restaurant_id))
            
            if not supabase_menu:
                logger.warning(f"No active menu found in Supabase for restaurant {restaurant_id}")
                return False
            
            # Get current cached menu
            current_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_id,
                is_active=True
            ).first()
            
            # Calculate checksum for new menu
            new_checksum = self.calculate_checksum(supabase_menu)
            
            if not new_checksum:
                raise ValueError("Failed to calculate menu checksum")
            
            # Check if update is needed
            if current_cache and current_cache.checksum == new_checksum:
                logger.info(f"Menu cache is already up to date for restaurant {restaurant_id}")
                return True
            
            # Create new cache entry
            new_version = current_cache.version + 1 if current_cache else 1
            
            with transaction.atomic():
                # Deactivate old cache if exists
                if current_cache:
                    current_cache.is_active = False
                    current_cache.save()
                
                # Create new cache
                new_cache = MenuCache.objects.create(
                    restaurant_id=restaurant_id,
                    menu_data=supabase_menu,
                    version=new_version,
                    checksum=new_checksum
                )
            
            # Update Redis cache
            cache_key = f"{self.cache_prefix}_{restaurant_id}"
            cache.set(cache_key, supabase_menu, self.cache_timeout)
            
            # Log activity
            ActivityLog.objects.create(
                restaurant_id=restaurant_id,
                level='INFO',
                module='MENU_CACHE',
                action='MENU_SYNC_COMPLETED',
                details={
                    'old_version': current_cache.version if current_cache else 0,
                    'new_version': new_version,
                    'menu_items_count': len(supabase_menu.get('items', [])),
                    'checksum_short': new_checksum[:16] + '...'
                }
            )
            
            logger.info(
                f"Menu cache updated for restaurant {restaurant_id} to version {new_version}",
                extra={'restaurant_id': restaurant_id, 'version': new_version}
            )
            
            return True
            
        except Restaurant.DoesNotExist:
            logger.error(f"Restaurant not found: {restaurant_id}")
            return False
        except Exception as e:
            # Log error
            ActivityLog.objects.create(
                restaurant_id=restaurant_id,
                level='ERROR',
                module='MENU_CACHE',
                action='MENU_SYNC_FAILED',
                details={'error': str(e)}
            )
            
            logger.error(
                f"Failed to sync menu from Supabase: {str(e)}",
                extra={'restaurant_id': restaurant_id},
                exc_info=True
            )
            return False
    
    def invalidate_cache(self, restaurant_id: str):
        """Invalidate cache for a restaurant"""
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        cache.delete(cache_key)
        logger.info(f"Menu cache invalidated for restaurant {restaurant_id}")
    
    def get_menu_version(self, restaurant_id: str) -> Optional[Dict]:
        """Get current menu version info"""
        try:
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_id,
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

# Service instance
menu_cache_service = MenuCacheService()