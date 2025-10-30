#CELERY SYNC TASKS


import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from apps.core.models import SyncQueue, ActivityLog
from apps.core.services.supabase_client import supabase_client
from .services import SyncManager

logger = logging.getLogger('dineswift')

@shared_task(
    name='apps.sync_manager.tasks.sync_pending_orders',
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def sync_pending_orders(self):
    
    #Sync pending orders to Supabase
    #UC-LOCAL-ORDER-105
   
    try:
        sync_manager = SyncManager()
        batch_size = settings.SYNC_CONFIG['batch_size']
        
        # Get pending sync items
        pending_items = SyncQueue.objects.filter(
            status='PENDING',
            sync_type__in=['ORDER_CREATE', 'ORDER_UPDATE']
        ).order_by('priority', 'created_at')[:batch_size]
        
        if not pending_items:
            logger.debug('No pending orders to sync')
            return {'synced': 0, 'failed': 0}
        
        synced_count = 0
        failed_count = 0
        
        for item in pending_items:
            try:
                success = sync_manager.process_sync_item(item)
                if success:
                    synced_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(
                    f'Failed to sync item {item.id}: {str(e)}',
                    exc_info=True
                )
                failed_count += 1
        
        logger.info(
            f'Sync completed: {synced_count} synced, {failed_count} failed',
            extra={
                'synced': synced_count,
                'failed': failed_count,
            }
        )
        
        return {'synced': synced_count, 'failed': failed_count}
        
    except Exception as e:
        logger.error(f'Sync task failed: {str(e)}', exc_info=True)
        raise self.retry(exc=e)

@shared_task(name='apps.sync_manager.tasks.retry_failed_syncs')
def retry_failed_syncs():
    
    #Retry failed sync operations
    
    try:
        sync_manager = SyncManager()
        
        # Get failed items ready for retry
        retry_items = SyncQueue.objects.filter(
            status='FAILED',
            next_retry__lte=timezone.now()
        ).order_by('priority', 'next_retry')[:50]
        
        retried_count = 0
        abandoned_count = 0
        
        for item in retry_items:
            if item.can_retry():
                success = sync_manager.process_sync_item(item)
                if success:
                    retried_count += 1
            else:
                item.status = 'CANCELLED'
                item.save()
                abandoned_count += 1
        
        logger.info(
            f'Retry completed: {retried_count} retried, {abandoned_count} abandoned'
        )
        
        return {'retried': retried_count, 'abandoned': abandoned_count}
        
    except Exception as e:
        logger.error(f'Retry task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}

@shared_task(name='apps.sync_manager.tasks.resolve_conflicts')
def resolve_conflicts():
  #Resolve sync conflicts using CRDT
    
    try:
        sync_manager = SyncManager()
        
        conflict_items = SyncQueue.objects.filter(
            status='CONFLICT'
        )[:20]
        
        resolved_count = 0
        
        for item in conflict_items:
            try:
                success = sync_manager.resolve_conflict(item)
                if success:
                    resolved_count += 1
            except Exception as e:
                logger.error(
                    f'Failed to resolve conflict for {item.id}: {str(e)}',
                    exc_info=True
                )
        
        logger.info(f'Conflict resolution: {resolved_count} resolved')
        
        return {'resolved': resolved_count}
        
    except Exception as e:
        logger.error(f'Conflict resolution task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}