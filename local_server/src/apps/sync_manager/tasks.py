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
    
"""
Celery Tasks for Sync Manager
Background tasks for synchronization operations with:
- Task state tracking
- Dead letter queue handling
- Progress reporting
- Graceful shutdown handling
"""

import logging
import time
from celery import shared_task, Task, states
from django.utils import timezone
from django.db import transaction, connection
from django.conf import settings
from django.core.cache import cache

from apps.core.models import SyncQueue, ActivityLog
from .services import SyncManager

logger = logging.getLogger('dineswift')


class SyncTask(Task):
    """Base sync task with common functionality"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        logger.error(f'Sync task {task_id} failed: {str(exc)}', exc_info=True)
        
        # Log to activity log if possible
        try:
            if args and len(args) > 0:
                sync_id = args[0]
                ActivityLog.objects.create(
                    level='ERROR',
                    module='CELERY',
                    action='SYNC_TASK_FAILED',
                    details={
                        'task_id': task_id,
                        'task_name': self.name,
                        'error': str(exc),
                        'sync_id': sync_id,
                    }
                )
        except Exception as e:
            logger.error(f'Failed to log task failure: {str(e)}')
        
        super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success"""
        logger.info(f'Sync task {task_id} completed successfully')
        super().on_success(retval, task_id, args, kwargs)


@shared_task(
    name='apps.sync_manager.tasks.sync_pending_orders',
    bind=True,
    base=SyncTask,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True
)
def sync_pending_orders(self, batch_size: int = None):
    """
    Sync pending orders to Supabase
    UC-LOCAL-ORDER-105
    """
    
    task_start = time.time()
    task_id = self.request.id
    
    try:
        sync_manager = SyncManager()
        batch_size = batch_size or settings.SYNC_CONFIG['batch_size']
        
        # Get database connection health
        try:
            connection.ensure_connection()
        except Exception as e:
            logger.error(f'Database connection failed: {str(e)}')
            raise self.retry(exc=e, countdown=30)
        
        # Get pending sync items with lock
        with transaction.atomic():
            pending_items = list(SyncQueue.objects.select_for_update(
                skip_locked=True
            ).filter(
                status='PENDING',
                sync_type__in=['ORDER_CREATE', 'ORDER_UPDATE'],
                next_retry__isnull=True  # Not scheduled for retry
            ).order_by('priority', 'created_at')[:batch_size])
        
        if not pending_items:
            logger.debug('No pending orders to sync')
            return {
                'task_id': task_id,
                'status': 'completed',
                'synced': 0,
                'failed': 0,
                'duration': time.time() - task_start,
            }
        
        # Update task state
        self.update_state(
            state=states.STARTED,
            meta={
                'total': len(pending_items),
                'processed': 0,
                'current': 0,
            }
        )
        
        synced_count = 0
        failed_count = 0
        failed_items = []
        
        for idx, item in enumerate(pending_items):
            try:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'total': len(pending_items),
                        'processed': idx,
                        'current': idx + 1,
                        'current_item': str(item.id),
                    }
                )
                
                success, error_msg = sync_manager.process_sync_item(item)
                if success:
                    synced_count += 1
                else:
                    failed_count += 1
                    failed_items.append({
                        'id': str(item.id),
                        'error': error_msg,
                    })
                    
            except Exception as e:
                logger.error(
                    f'Failed to sync item {item.id}: {str(e)}',
                    exc_info=True
                )
                failed_count += 1
                failed_items.append({
                    'id': str(item.id),
                    'error': str(e),
                })
        
        task_duration = time.time() - task_start
        
        # Log task completion
        ActivityLog.objects.create(
            level='INFO',
            module='CELERY',
            action='SYNC_TASK_COMPLETED',
            details={
                'task_id': task_id,
                'task_name': self.name,
                'total_items': len(pending_items),
                'synced': synced_count,
                'failed': failed_count,
                'duration': task_duration,
                'failed_items': failed_items[:10],  # Limit failed items in log
            }
        )
        
        logger.info(
            f'Sync completed: {synced_count} synced, {failed_count} failed',
            extra={
                'task_id': task_id,
                'synced': synced_count,
                'failed': failed_count,
                'duration': task_duration,
            }
        )
        
        return {
            'task_id': task_id,
            'status': 'completed',
            'total': len(pending_items),
            'synced': synced_count,
            'failed': failed_count,
            'duration': task_duration,
            'failed_items': failed_items,
        }
        
    except Exception as e:
        logger.error(f'Sync task failed: {str(e)}', exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name='apps.sync_manager.tasks.retry_failed_syncs',
    bind=True,
    base=SyncTask,
    max_retries=2,
    default_retry_delay=300
)
def retry_failed_syncs(self):
    """
    Retry failed sync operations
    """
    
    try:
        sync_manager = SyncManager()
        
        # Get failed items ready for retry
        retry_items = SyncQueue.objects.filter(
            status='FAILED',
            next_retry__lte=timezone.now(),
            retry_count__lt=models.F('max_retries')
        ).order_by('priority', 'next_retry')[:50]
        
        retried_count = 0
        abandoned_count = 0
        results = []
        
        for item in retry_items:
            try:
                success, error_msg = sync_manager.process_sync_item(item)
                if success:
                    retried_count += 1
                    results.append({
                        'id': str(item.id),
                        'status': 'success',
                    })
                else:
                    results.append({
                        'id': str(item.id),
                        'status': 'failed',
                        'error': error_msg,
                    })
            except Exception as e:
                logger.error(f'Failed to retry item {item.id}: {str(e)}')
                results.append({
                    'id': str(item.id),
                    'status': 'error',
                    'error': str(e),
                })
        
        # Mark items that exceeded max retries as abandoned
        abandoned_items = SyncQueue.objects.filter(
            status='FAILED',
            retry_count=models.F('max_retries'),
            next_retry__lte=timezone.now()
        )
        
        abandoned_count = abandoned_items.update(status='CANCELLED')
        
        logger.info(
            f'Retry completed: {retried_count} retried, {abandoned_count} abandoned'
        )
        
        return {
            'retried': retried_count,
            'abandoned': abandoned_count,
            'results': results,
        }
        
    except Exception as e:
        logger.error(f'Retry task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}

@shared_task(
    name='apps.sync_manager.tasks.health_check_sync',
    bind=True,
    base=SyncTask
)
def health_check_sync(self):
    """
    Health check for sync system
    """
    
    health_data = {
        'status': 'healthy',
        'checks': {},
        'timestamp': timezone.now().isoformat(),
    }
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM sync_queue WHERE status = %s', ['PENDING'])
            pending_count = cursor.fetchone()[0]
        
        health_data['checks']['database'] = {
            'status': 'healthy',
            'pending_items': pending_count,
        }
    except Exception as e:
        health_data['checks']['database'] = {
            'status': 'unhealthy',
            'error': str(e),
        }
        health_data['status'] = 'unhealthy'
    
    # Check cache
    try:
        cache_key = 'sync_health_check'
        cache.set(cache_key, 'ok', 10)
        cache_ok = cache.get(cache_key) == 'ok'
        
        health_data['checks']['cache'] = {
            'status': 'healthy' if cache_ok else 'unhealthy',
        }
        if not cache_ok:
            health_data['status'] = 'unhealthy'
    except Exception as e:
        health_data['checks']['cache'] = {
            'status': 'unhealthy',
            'error': str(e),
        }
        health_data['status'] = 'unhealthy'
    
    # Check Supabase connectivity
    try:
        supabase_healthy = supabase_client.health_check()
        health_data['checks']['supabase'] = {
            'status': 'healthy' if supabase_healthy else 'unhealthy',
            'available': supabase_client.is_available(),
        }
        if not supabase_healthy:
            health_data['status'] = 'unhealthy'
    except Exception as e:
        health_data['checks']['supabase'] = {
            'status': 'unhealthy',
            'error': str(e),
        }
        health_data['status'] = 'unhealthy'
    
    # Check queue health
    try:
        stale_items = SyncQueue.objects.filter(
            status='PROCESSING',
            updated_at__lt=timezone.now() - timezone.timedelta(minutes=30)
        ).count()
        
        health_data['checks']['queue'] = {
            'status': 'healthy' if stale_items == 0 else 'warning',
            'stale_items': stale_items,
        }
        if stale_items > 10:
            health_data['status'] = 'warning'
    except Exception as e:
        health_data['checks']['queue'] = {
            'status': 'unhealthy',
            'error': str(e),
        }
        health_data['status'] = 'unhealthy'
    
    return health_data

@shared_task(
    name='apps.sync_manager.tasks.resolve_conflicts',
    bind=True,
    base=SyncTask,
    max_retries=2
)
def resolve_conflicts(self, strategy: str = None):
    """
    Enhanced conflict resolution task with multiple strategies
    """
    try:
        from .services import SyncManager
        from .conflict_resolution import ConflictResolutionStrategy
        
        sync_manager = SyncManager()
        
        # Get conflict items
        conflict_items = SyncQueue.objects.filter(
            status='CONFLICT',
            updated_at__gte=timezone.now() - timedelta(hours=24)  # Only recent conflicts
        ).order_by('priority', 'created_at')[:20]
        
        resolution_results = {
            'total': len(conflict_items),
            'resolved': 0,
            'failed': 0,
            'by_strategy': {},
            'details': [],
        }
        
        for item in conflict_items:
            try:
                # Resolve conflict
                success, error, details = sync_manager.resolve_conflict(item, strategy)
                
                result_detail = {
                    'sync_id': str(item.id),
                    'success': success,
                    'error': error,
                    'strategy': strategy or 'auto',
                    'details': details,
                }
                
                if success:
                    resolution_results['resolved'] += 1
                else:
                    resolution_results['failed'] += 1
                
                # Track strategy usage
                used_strategy = details.get('strategy', 'unknown')
                resolution_results['by_strategy'][used_strategy] = \
                    resolution_results['by_strategy'].get(used_strategy, 0) + 1
                
                resolution_results['details'].append(result_detail)
                
            except Exception as e:
                logger.error(
                    f'Failed to resolve conflict for {item.id}: {str(e)}',
                    exc_info=True
                )
                resolution_results['failed'] += 1
                resolution_results['details'].append({
                    'sync_id': str(item.id),
                    'success': False,
                    'error': str(e),
                })
        
        logger.info(
            f'Conflict resolution completed: {resolution_results["resolved"]} resolved, '
            f'{resolution_results["failed"]} failed'
        )
        
        # Update global metrics
        metrics_key = 'conflict_metrics:global'
        metrics = cache.get(metrics_key, {
            'total_resolutions': 0,
            'successful_resolutions': 0,
            'failed_resolutions': 0,
            'last_run': None,
        })
        
        metrics['total_resolutions'] += resolution_results['total']
        metrics['successful_resolutions'] += resolution_results['resolved']
        metrics['failed_resolutions'] += resolution_results['failed']
        metrics['last_run'] = timezone.now().isoformat()
        
        cache.set(metrics_key, metrics, 86400)  # 24 hours
        
        return resolution_results
        
    except Exception as e:
        logger.error(f'Conflict resolution task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}


@shared_task(
    name='apps.sync_manager.tasks.manual_conflict_review',
    bind=True,
    base=SyncTask
)
def manual_conflict_review(self):
    """
    Task to identify conflicts requiring manual intervention
    """
    try:
        # Get conflicts that need manual review
        conflicts_needing_review = SyncQueue.objects.filter(
            status='CONFLICT',
            conflict_data__preferred_resolution='manual_intervention'
        ).order_by('-priority', 'created_at')[:50]
        
        # Get conflicts with multiple failed resolution attempts
        conflicts_with_failures = SyncQueue.objects.filter(
            status='CONFLICT',
            conflict_data__resolution_attempts__length__gte=3
        ).order_by('created_at')[:50]
        
        all_conflicts = list(conflicts_needing_review) + list(conflicts_with_failures)
        unique_conflicts = {conflict.id: conflict for conflict in all_conflicts}.values()
        
        # Create review notifications
        review_items = []
        for conflict in unique_conflicts:
            review_items.append({
                'id': str(conflict.id),
                'restaurant_id': str(conflict.restaurant_id),
                'sync_type': conflict.sync_type,
                'created_at': conflict.created_at.isoformat(),
                'conflict_summary': conflict.conflict_data.get('conflict_info', {}) if conflict.conflict_data else {},
                'resolution_attempts': len(conflict.conflict_data.get('resolution_attempts', [])) if conflict.conflict_data else 0,
                'priority': conflict.priority,
            })
        
        # Store for admin UI
        cache_key = 'manual_conflict_review:queue'
        cache.set(cache_key, review_items, 3600)  # 1 hour
        
        return {
            'total_conflicts': len(unique_conflicts),
            'needing_manual_review': len(conflicts_needing_review),
            'with_failed_attempts': len(conflicts_with_failures),
            'review_items': review_items,
        }
        
    except Exception as e:
        logger.error(f'Manual conflict review task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}