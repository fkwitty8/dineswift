"""
Modern Service - Flutter App with Enhanced Features
"""
import logging
import uuid
import time
from typing import Dict, Optional, List, Any
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone

from .legacy_services import LegacyMenuService
from apps.core.models import ActivityLog
from apps.core.services.supabase_client import supabase_client
from apps.menu_cache.models import MenuCache

logger = logging.getLogger('dineswift')

class ModernMenuService(LegacyMenuService):
    """
    Modern service for Flutter app with enhanced features
    Inherits from LegacyMenuService for backward compatibility
    UC-MODERN-001: Flutter app menu operations
    """
    
    def __init__(self):
        super().__init__()
        self.flutter_format_version = "2.0"
        self.cache_timeout = 1800  # 30 minutes for more freshness
        self.cache_prefix = "menu_flutter"
    
    def get_menu_for_flutter(self, restaurant_id: str, 
                           include_customizations: bool = False,
                           include_dietary_info: bool = True) -> Optional[Dict]:
        """
        Get menu optimized for Flutter app
        UC-MODERN-002: Enhanced menu retrieval
        """
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        
        start_time = time.time()
        
        try:
            # Try cache with Flutter optimization
            cached_menu = cache.get(cache_key)
            if cached_menu:
                logger.debug(f"Flutter cache HIT for restaurant {restaurant_id}")
                return self.enhance_for_flutter(cached_menu, include_customizations, include_dietary_info)
        except Exception as e:
            logger.warning(f"Flutter cache error: {str(e)}")
        
        # Fallback to database with performance tracking
        try:
            restaurant_uuid = uuid.UUID(restaurant_id)
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_uuid,
                is_active=True
            ).select_related('restaurant').first()
            
            if menu_cache:
                # Enhance for Flutter
                enhanced_menu = self.enhance_for_flutter(
                    menu_cache.menu_data,
                    include_customizations,
                    include_dietary_info
                )
                
                # Add metadata
                enhanced_menu['metadata'] = self._generate_metadata(menu_cache)
                
                # Cache enhanced data
                try:
                    cache.set(cache_key, menu_cache.menu_data, self.cache_timeout)
                except Exception as e:
                    logger.warning(f"Flutter cache set error: {str(e)}")
                
                load_time = time.time() - start_time
                logger.info(f"Flutter menu loaded in {load_time:.2f}s for {restaurant_id}")
                
                return enhanced_menu
        
        except Exception as e:
            logger.error(f"Flutter menu fetch failed: {str(e)}")
        
        return None
    
    def enhance_for_flutter(self, menu_data: Dict, 
                          include_customizations: bool,
                          include_dietary_info: bool) -> Dict:
        """Enhance menu data for Flutter app"""
        if not menu_data:
            return {}
        
        enhanced = {
            'version': self.flutter_format_version,
            'restaurant': menu_data.get('restaurant_info', {}),
            'categories': [],
            'features': {
                'supports_images': True,
                'supports_customizations': include_customizations,
                'supports_dietary_filters': include_dietary_info
            }
        }
        
        # Enhance categories and items
        for category in menu_data.get('categories', []):
            flutter_category = {
                'id': str(category.get('id', '')),
                'name': category.get('name', ''),
                'description': category.get('description', ''),
                'display_order': category.get('display_order', 0),
                'icon': category.get('icon', ''),
                'color': category.get('color', '#4CAF50'),
                'items': []
            }
            
            for item in category.get('items', []):
                flutter_item = {
                    'id': str(item.get('id', '')),
                    'name': item.get('name', ''),
                    'description': item.get('description', ''),
                    'price': item.get('price', 0),
                    'display_price': f"${item.get('price', 0):.2f}",
                    'category_id': str(category.get('id', '')),
                    'category_name': category.get('name', ''),
                    'is_available': item.get('is_available', True),
                    'in_stock': item.get('in_stock', True),
                    'image_url': item.get('image_url'),
                    'thumbnail_url': item.get('thumbnail_url'),
                    'preparation_time': item.get('preparation_time', 15),
                    'spice_level': item.get('spice_level', 0)
                }
                
                # Add dietary info if requested
                if include_dietary_info:
                    flutter_item['dietary_tags'] = item.get('dietary_tags', [])
                    flutter_item['allergens'] = item.get('allergens', [])
                
                # Add customizations if requested
                if include_customizations:
                    flutter_item['customizations'] = self._get_customizations(item)
                
                flutter_category['items'].append(flutter_item)
            
            enhanced['categories'].append(flutter_category)
        
        return enhanced
    
    def _get_customizations(self, item: Dict) -> List[Dict]:
        """Extract customizations for an item"""
        customizations = item.get('customizations', [])
        return [
            {
                'id': str(cust.get('id', '')),
                'name': cust.get('name', ''),
                'type': cust.get('type', 'single'),
                'options': cust.get('options', []),
                'required': cust.get('required', False)
            }
            for cust in customizations
        ]
    
    def _generate_metadata(self, menu_cache: MenuCache) -> Dict:
        """Generate metadata for Flutter app"""
        menu_data = menu_cache.menu_data or {}
        categories = menu_data.get('categories', [])
        
        total_items = sum(len(category.get('items', [])) for category in categories)
        
        return {
            'generated_at': timezone.now().isoformat(),
            'items_count': total_items,
            'categories_count': len(categories),
            'checksum': menu_cache.checksum,
            'version': menu_cache.version,
            'freshness': self._calculate_freshness(menu_cache.last_synced)
        }
    
    def _calculate_freshness(self, last_synced) -> str:
        """Calculate freshness of menu data"""
        delta = timezone.now() - last_synced
        
        if delta.days > 7:
            return 'stale'
        elif delta.days > 1:
            return 'recent'
        elif delta.seconds > 3600:
            return 'fresh'
        else:
            return 'very_fresh'
    
    async def sync_menu_with_enhancements(self, restaurant_id: str, 
                                        force_refresh: bool = False) -> bool:
        """
        Enhanced sync with Flutter optimizations
        UC-MODERN-003: Smart menu sync
        """
        try:
            if force_refresh:
                self.invalidate_cache(restaurant_id)
            
            restaurant = await sync_to_async(self._get_restaurant)(restaurant_id)
            if not restaurant:
                logger.error(f"Flutter: Restaurant not found: {restaurant_id}")
                return False
            
            # Fetch enhanced menu from Supabase
            supabase_menu = await supabase_client.get_menu_with_enhancements(
                str(restaurant.supabase_restaurant_id),
                include_images=True,
                include_customizations=True
            )
            
            if not supabase_menu:
                logger.warning(f"Flutter: No enhanced menu found")
                return False
            
            # Enhance for Flutter
            enhanced_menu = self.enhance_for_flutter(supabase_menu, True, True)
            
            # Save to database
            success = await sync_to_async(self._save_menu_to_db)(
                restaurant_id,
                enhanced_menu
            )
            
            if success:
                # Log success
                await sync_to_async(ActivityLog.objects.create)(
                    restaurant_id=restaurant.id,
                    level='INFO',
                    module='FLUTTER_MENU_CACHE',
                    action='FLUTTER_MENU_SYNC_SUCCESS',
                    details={'version': self.flutter_format_version}
                )
                
                logger.info(f"Flutter menu synced for restaurant {restaurant_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Flutter sync failed: {str(e)}", exc_info=True)
            return False
    
    def get_cache_insights(self, restaurant_id: str) -> Dict:
        """Get cache performance insights"""
        cache_key = f"{self.cache_prefix}_{restaurant_id}"
        
        try:
            # Get cache info (you might need to implement this in your cache backend)
            # This is a placeholder
            return {
                'cache_key': cache_key,
                'timeout': self.cache_timeout,
                'estimated_size': 'unknown',
                'last_accessed': 'unknown'
            }
        except Exception as e:
            logger.warning(f"Cache insights error: {str(e)}")
            return {}
    
    def get_cache_hit_rate(self, restaurant_id: str) -> float:
        """Calculate cache hit rate (placeholder)"""
        # Implement actual tracking in production
        return 0.85
    
    def get_average_load_time(self, restaurant_id: str) -> float:
        """Get average menu load time (placeholder)"""
        # Implement actual tracking in production
        return 0.15
    
    def start_async_refresh(self, restaurant_id: str) -> str:
        """Start async refresh and return tracking ID"""
        refresh_id = str(uuid.uuid4())
        # In production, use Celery or Django Channels
        logger.info(f"Started async refresh {refresh_id} for {restaurant_id}")
        return refresh_id
    
    def preload_menu(self, restaurant_id: str) -> bool:
        """Preload menu for better UX"""
        try:
            menu_data = self.get_menu_for_flutter(restaurant_id, True, True)
            return menu_data is not None
        except Exception as e:
            logger.error(f"Preload failed: {str(e)}")
            return False
    
    def get_last_sync_time(self, restaurant_id: str) -> Optional[str]:
        """Get last sync timestamp"""
        try:
            restaurant_uuid = uuid.UUID(restaurant_id)
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_uuid,
                is_active=True
            ).first()
            
            if menu_cache:
                return menu_cache.last_synced.isoformat()
            return None
        except Exception as e:
            logger.error(f"Failed to get sync time: {str(e)}")
            return None

# Service instance
modern_menu_service = ModernMenuService()