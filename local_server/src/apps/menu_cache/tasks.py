#MENU SYNC TASKS

import logging
from celery import shared_task
from apps.core.models import Restaurant
from .services import MenuCacheService

logger = logging.getLogger('dineswift')

@shared_task(name='apps.menu_cache.tasks.sync_all_restaurant_menus')
def sync_all_restaurant_menus():
    #Sync menus for all active restaurants
    
    try:
        menu_service = MenuCacheService()
        restaurants = Restaurant.objects.filter(is_active=True)
        
        synced_count = 0
        failed_count = 0
        
        for restaurant in restaurants:
            try:
                success = menu_service.sync_menu_from_supabase(str(restaurant.id))
                if success:
                    synced_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(
                    f'Failed to sync menu for restaurant {restaurant.id}: {str(e)}',
                    exc_info=True
                )
                failed_count += 1
        
        logger.info(
            f'Menu sync completed: {synced_count} synced, {failed_count} failed'
        )
        
        return {'synced': synced_count, 'failed': failed_count}
        
    except Exception as e:
        logger.error(f'Menu sync task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}

@shared_task(name='apps.menu_cache.tasks.sync_single_restaurant_menu')
def sync_single_restaurant_menu(restaurant_id: str):
   # Sync menu for a single restaurant
   
    try:
        menu_service = MenuCacheService()
        success = menu_service.sync_menu_from_supabase(restaurant_id)
        
        return {'success': success, 'restaurant_id': restaurant_id}
        
    except Exception as e:
        logger.error(f'Single menu sync failed: {str(e)}', exc_info=True)
        return {'success': False, 'error': str(e)}