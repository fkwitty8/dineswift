import logging
import hashlib
import json
import uuid
from typing import Dict, Optional
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
from asgiref.sync import sync_to_async
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
        try:
            cached_menu = cache.get(cache_key)
            if cached_menu:
                logger.debug(f"Menu cache HIT for restaurant {restaurant_id}")
                return cached_menu
        except Exception as e:
            logger.warning(f"Cache error for restaurant {restaurant_id}: {str(e)}")
            # Continue to database fallback
        
        # Fallback to database
        try:
            # Convert string ID to UUID for database query
            restaurant_uuid = uuid.UUID(restaurant_id)
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_uuid,
                is_active=True
            ).first()
            
            if menu_cache:
                # Cache in Redis for future requests
                try:
                    cache.set(cache_key, menu_cache.menu_data, self.cache_timeout)
                except Exception as e:
                    logger.warning(f"Cache set error for restaurant {restaurant_id}: {str(e)}")
                
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
            print(f"\n[DEBUG] Starting sync for restaurant_id: {restaurant_id}")
            
            # Convert string ID to UUID for database query
            try:
                restaurant_uuid = uuid.UUID(restaurant_id)
                print(f"[DEBUG] Converted to UUID: {restaurant_uuid}")
            except ValueError as e:
                logger.error(f"Invalid restaurant ID format: {restaurant_id} - {e}")
                return False
            
            # Get restaurant with sync_to_async
            print(f"[DEBUG] Querying database for restaurant...")
            restaurant = await sync_to_async(
                Restaurant.objects.filter(id=restaurant_uuid).first
            )()
            
            print(f"[DEBUG] Restaurant query result: {restaurant}")
            
            if not restaurant:
                logger.error(f"Restaurant not found: {restaurant_id}")
                print(f"[DEBUG] RESTAURANT NOT FOUND! UUID used: {restaurant_uuid}")
                
                # Let's check what restaurants exist
                all_restaurants = await sync_to_async(list)(Restaurant.objects.all())
                print(f"[DEBUG] All restaurants in DB: {[str(r.id) for r in all_restaurants]}")
                
                return False
            
            print(f"[DEBUG] Restaurant found: {restaurant.name}")
            
            # Rest of the method remains the same...
            supabase_client.set_restaurant_context(str(restaurant.supabase_restaurant_id))
            
            # Fetch latest menu from Supabase
            supabase_menu = await supabase_client.get_menu(str(restaurant.supabase_restaurant_id))
            
            if not supabase_menu:
                logger.warning(f"No active menu found in Supabase for restaurant {restaurant_id}")
                return False
                        
        except Exception as e:
            # Log error with sync_to_async
            try:
                # Convert string ID to UUID for activity log
                restaurant_uuid = uuid.UUID(restaurant_id)
                await sync_to_async(ActivityLog.objects.create)(
                    restaurant_id=restaurant_uuid,
                    level='ERROR',
                    module='MENU_CACHE',
                    action='MENU_SYNC_FAILED',
                    details={'error': str(e)}
                )
            except Exception:
                pass
            
            logger.error(
                f"Failed to sync menu from Supabase: {str(e)}",
                extra={'restaurant_id': restaurant_id},
                exc_info=True
            )
            return False
    
    def invalidate_cache(self, restaurant_id: str):
        """Invalidate cache for a restaurant"""
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        try:
            cache.delete(cache_key)
            logger.info(f"Menu cache invalidated for restaurant {restaurant_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation error for restaurant {restaurant_id}: {str(e)}")
    
    def get_menu_version(self, restaurant_id: str) -> Optional[Dict]:
        """Get current menu version info"""
        try:
            # Convert string ID to UUID for database query
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

# Service instance
menu_cache_service = MenuCacheService()