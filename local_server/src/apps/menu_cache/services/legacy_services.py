"""
Legacy Service - Mobile App Compatibility
"""
import logging
from typing import Dict, Optional, List
from asgiref.sync import sync_to_async
from django.db import transaction

import uuid

from .base import BaseMenuService
from apps.core.models import ActivityLog
from apps.core.services.supabase_client import supabase_client
from apps.menu_cache.models import MenuCache

from django.core.cache import cache

logger = logging.getLogger('dineswift')

class LegacyMenuService(BaseMenuService):
    """
    Service for legacy mobile app compatibility
    UC-LEGACY-001: Mobile app menu operations
    """
    
    def __init__(self):
        super().__init__()
        self.legacy_format_version = "1.0"
    
    def get_cached_menu(self, restaurant_id: str) -> Optional[Dict]:
        """Get menu with legacy mobile app compatibility"""
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        
        # Try Redis cache
        try:
            cached_menu = cache.get(cache_key)
            if cached_menu:
                logger.debug(f"Legacy cache HIT for restaurant {restaurant_id}")
                return self.transform_for_mobile(cached_menu)
        except Exception as e:
            logger.warning(f"Legacy cache error: {str(e)}")
        
        # Fallback to database
        try:
            restaurant_uuid = uuid.UUID(restaurant_id)
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_uuid,
                is_active=True
            ).first()
            
            if menu_cache:
                # Transform for mobile
                transformed_menu = self.transform_for_mobile(menu_cache.menu_data)
                
                # Cache transformed data
                try:
                    cache.set(cache_key, menu_cache.menu_data, self.cache_timeout)
                except Exception as e:
                    logger.warning(f"Cache set error: {str(e)}")
                
                logger.debug(f"Legacy menu loaded from DB for restaurant {restaurant_id}")
                return transformed_menu
        
        except Exception as e:
            logger.error(f"Legacy menu fetch failed: {str(e)}")
        
        return None
    
    def transform_for_mobile(self, menu_data: Dict) -> Dict:
        """Transform menu data for legacy mobile app compatibility"""
        if not menu_data:
            return {}
        
        transformed = {
            'version': self.legacy_format_version,
            'restaurant_info': menu_data.get('restaurant_info', {}),
            'categories': []
        }
        
        # Transform categories and items for mobile
        for category in menu_data.get('categories', []):
            mobile_category = {
                'id': str(category.get('id', '')),
                'name': category.get('name', ''),
                'display_order': category.get('display_order', 0),
                'items': []
            }
            
            for item in category.get('items', []):
                mobile_item = {
                    'id': str(item.get('id', '')),
                    'name': item.get('name', ''),
                    'description': item.get('description', ''),
                    'price': str(item.get('price', '0.00')),
                    'category': category.get('name', ''),
                    'is_available': item.get('is_available', True),
                    'item_code': item.get('item_code', ''),
                    'tax_rate': str(item.get('tax_rate', '0.00')),
                    'discount_eligible': item.get('discount_eligible', False)
                }
                mobile_category['items'].append(mobile_item)
            
            transformed['categories'].append(mobile_category)
        
        return transformed
    
    async def sync_menu_from_supabase(self, restaurant_id: str) -> bool:
        """
        Sync menu from Supabase with legacy compatibility
        UC-LEGACY-002: Mobile app menu sync
        """
        try:
            print(f"\n[LEGACY] Starting sync for restaurant_id: {restaurant_id}")
            
            restaurant = await sync_to_async(self._get_restaurant)(restaurant_id)
            if not restaurant:
                logger.error(f"Legacy: Restaurant not found: {restaurant_id}")
                return False
            
            print(f"[LEGACY] Restaurant found: {restaurant.name}")
            
            # Set context for legacy mobile app
            supabase_client.set_restaurant_context(str(restaurant.supabase_restaurant_id))
            
            # Fetch legacy-compatible menu
            supabase_menu = await supabase_client.get_menu_for_mobile(
                str(restaurant.supabase_restaurant_id)
            )
            
            if not supabase_menu:
                logger.warning(f"Legacy: No active menu found in Supabase")
                return False
            
            # Transform for legacy compatibility
            legacy_menu = self.transform_for_mobile(supabase_menu)
            
            # Save to database
            success = await sync_to_async(self._save_menu_to_db)(
                restaurant_id,
                legacy_menu
            )
            
            if success:
                # Log activity
                await sync_to_async(ActivityLog.objects.create)(
                    restaurant_id=restaurant.id,
                    level='INFO',
                    module='LEGACY_MENU_CACHE',
                    action='LEGACY_MENU_SYNC_SUCCESS',
                    details={'version': self.legacy_format_version}
                )
                
                logger.info(f"Legacy menu synced for restaurant {restaurant_id}")
                return True
            else:
                return False
                        
        except Exception as e:
            # Log error
            try:
                restaurant_uuid = uuid.UUID(restaurant_id)
                await sync_to_async(ActivityLog.objects.create)(
                    restaurant_id=restaurant_uuid,
                    level='ERROR',
                    module='LEGACY_MENU_CACHE',
                    action='LEGACY_MENU_SYNC_FAILED',
                    details={'error': str(e)}
                )
            except Exception:
                pass
            
            logger.error(f"Legacy sync failed: {str(e)}", exc_info=True)
            return False
    
    def force_sync(self, restaurant_id: str) -> bool:
        """Force sync for legacy system"""
        try:
            # Clear cache first
            self.invalidate_cache(restaurant_id)
            
            # Perform sync
            # Note: This is a synchronous wrapper around async method
            # In production, you might want to use sync_to_async
            import asyncio
            return asyncio.run(self.sync_menu_from_supabase(restaurant_id))
        except Exception as e:
            logger.error(f"Legacy force sync failed: {str(e)}")
            return False

# Service instance
legacy_menu_service = LegacyMenuService()