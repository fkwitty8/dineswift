#MAINTENANCE TASKS


import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db import connection
from django.core.cache import cache

from apps.core.models import ActivityLog, HealthCheck
from apps.core.services.supabase_client import supabase_client
from apps.otp_service.services import OTPService

logger = logging.getLogger('dineswift')

@shared_task(name='apps.core.tasks.cleanup_old_logs')
def cleanup_old_logs():
    #Delete logs older than 30 days
   
    try:
        cutoff_date = timezone.now() - timedelta(days=30)
        
        deleted_count = ActivityLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f'Deleted {deleted_count} old log entries')
        
        # Cleanup expired OTPs
        otp_service = OTPService()
        otp_count = otp_service.cleanup_expired_otps()
        
        return {
            'logs_deleted': deleted_count,
            'otps_cleaned': otp_count
        }
        
    except Exception as e:
        logger.error(f'Cleanup task failed: {str(e)}', exc_info=True)
        return {'error': str(e)}

@shared_task(name='apps.core.tasks.perform_health_check')
def perform_health_check():
    #Perform system health checks
    
    results = {}
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        db_healthy = True
        db_time = 0
    except Exception as e:
        db_healthy = False
        db_time = None
        logger.error(f'Database health check failed: {str(e)}')
    
    HealthCheck.objects.update_or_create(
        component='DATABASE',
        defaults={
            'is_healthy': db_healthy,
            'response_time_ms': db_time,
            'error_message': '' if db_healthy else 'Connection failed'
        }
    )
    results['database'] = db_healthy
    
    # Check Redis
    try:
        cache.set('health_check', 'ok', 10)
        redis_healthy = cache.get('health_check') == 'ok'
        redis_time = 0
    except Exception as e:
        redis_healthy = False
        redis_time = None
        logger.error(f'Redis health check failed: {str(e)}')
    
    HealthCheck.objects.update_or_create(
        component='REDIS',
        defaults={
            'is_healthy': redis_healthy,
            'response_time_ms': redis_time,
            'error_message': '' if redis_healthy else 'Connection failed'
        }
    )
    results['redis'] = redis_healthy
    
    # Check Supabase
    try:
        supabase_healthy = supabase_client.health_check()
    except Exception as e:
        supabase_healthy = False
        logger.error(f'Supabase health check failed: {str(e)}')
    
    HealthCheck.objects.update_or_create(
        component='SUPABASE',
        defaults={
            'is_healthy': supabase_healthy,
            'error_message': '' if supabase_healthy else 'Connection failed'
        }
    )
    results['supabase'] = supabase_healthy
    
    logger.info(f'Health check completed: {results}')
    
    return results