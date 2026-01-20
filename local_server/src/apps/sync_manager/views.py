import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q

from .tasks import sync_pending_orders, retry_failed_syncs
from apps.core.models import SyncQueue
from apps.core.serializers import SyncQueueSerializer

logger = logging.getLogger('dineswift')
        

"""
API endpoints with:
- Request validation
- Comprehensive error handling
- Pagination support
- Metrics endpoint
- Admin endpoints
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q, F, Sum, Avg
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

from .tasks import sync_pending_orders, retry_failed_syncs, health_check_sync
from apps.core.models import SyncQueue, ActivityLog
from apps.core.serializers import SyncQueueSerializer
from .services import SyncManager

logger = logging.getLogger('dineswift')


class SyncPagination(PageNumberPagination):
    """Custom pagination for sync queue"""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sync_status(request):
    """Get comprehensive synchronization status for the restaurant"""
    try:
        restaurant_id = request.user.restaurant_id
        
        # Get sync statistics
        stats = SyncQueue.objects.filter(
            restaurant_id=restaurant_id
        ).aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            processing=Count('id', filter=Q(status='PROCESSING')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            failed=Count('id', filter=Q(status='FAILED')),
            conflict=Count('id', filter=Q(status='CONFLICT')),
            cancelled=Count('id', filter=Q(status='CANCELLED')),
            avg_retry_count=Avg('retry_count', filter=Q(status='FAILED')),
        )
        
        # Get sync metrics by type
        metrics_by_type = SyncQueue.objects.filter(
            restaurant_id=restaurant_id
        ).values('sync_type').annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            failed=Count('id', filter=Q(status='FAILED')),
            avg_retry=Avg('retry_count'),
        ).order_by('sync_type')
        
        # Get recent activities
        recent_activities = ActivityLog.objects.filter(
            restaurant_id=restaurant_id,
            module='SYNC_MANAGER'
        ).order_by('-created_at')[:10]
        
        # Get sync performance metrics
        sync_manager = SyncManager()
        performance_metrics = sync_manager.get_sync_metrics(restaurant_id)
        
        # Calculate success rate
        total_completed = stats.get('completed', 0)
        total_failed = stats.get('failed', 0)
        total_processed = total_completed + total_failed
        success_rate = (total_completed / total_processed * 100) if total_processed > 0 else 0
        
        return Response({
            'statistics': stats,
            'metrics_by_type': metrics_by_type,
            'performance': performance_metrics,
            'success_rate': round(success_rate, 2),
            'recent_activities': [
                {
                    'level': activity.level,
                    'action': activity.action,
                    'details': activity.details,
                    'created_at': activity.created_at,
                }
                for activity in recent_activities
            ]
        })
        
    except Exception as e:
        logger.error(f"Failed to get sync status: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to retrieve sync status', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sync_queue(request):
    """Get current sync queue items with pagination and filtering"""
    try:
        restaurant_id = request.user.restaurant_id
        
        # Get filters from query params
        status_filter = request.GET.get('status')
        sync_type_filter = request.GET.get('sync_type')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Build query
        query = Q(restaurant_id=restaurant_id)
        
        if status_filter:
            query &= Q(status=status_filter)
        
        if sync_type_filter:
            query &= Q(sync_type=sync_type_filter)
        
        if start_date:
            query &= Q(created_at__gte=start_date)
        
        if end_date:
            query &= Q(created_at__lte=end_date)
        
        queue_items = SyncQueue.objects.filter(query).order_by('priority', 'created_at')
        
        # Paginate results
        paginator = SyncPagination()
        page = paginator.paginate_queryset(queue_items, request)
        
        if page is not None:
            serializer = SyncQueueSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = SyncQueueSerializer(queue_items, many=True)
        return Response(serializer.data)
        
    except ValueError as e:
        logger.warning(f"Invalid query parameter: {str(e)}")
        return Response(
            {'error': 'Invalid query parameter', 'detail': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Failed to get sync queue: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to retrieve sync queue', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def retry_failed_syncs_view(request):
    """Manually retry failed sync operations"""
    try:
        # Get filter parameters
        max_age_hours = request.data.get('max_age_hours', 24)
        sync_type = request.data.get('sync_type')
        
        # Calculate cutoff time
        cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
        
        # Trigger the retry task with parameters
        result = retry_failed_syncs.delay()
        
        # Log manual retry
        ActivityLog.objects.create(
            restaurant_id=request.user.restaurant_id,
            level='INFO',
            module='SYNC_MANAGER',
            action='MANUAL_RETRY_TRIGGERED',
            details={
                'task_id': result.id,
                'max_age_hours': max_age_hours,
                'sync_type': sync_type,
                'triggered_by': str(request.user.id),
            }
        )
        
        return Response({
            'status': 'success',
            'message': 'Retry task queued successfully',
            'task_id': result.id,
            'parameters': {
                'max_age_hours': max_age_hours,
                'sync_type': sync_type,
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to queue retry task: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to queue retry task', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def force_sync(request):
    """Force immediate synchronization with options"""
    try:
        # Get options from request
        limit = request.data.get('limit', 100)
        sync_types = request.data.get('sync_types', ['ORDER_CREATE', 'ORDER_UPDATE'])
        
        # Trigger sync task immediately with parameters
        result = sync_pending_orders.delay(batch_size=limit)
        
        # Log force sync
        ActivityLog.objects.create(
            restaurant_id=request.user.restaurant_id,
            level='INFO',
            module='SYNC_MANAGER',
            action='FORCE_SYNC_TRIGGERED',
            details={
                'task_id': result.id,
                'limit': limit,
                'sync_types': sync_types,
                'triggered_by': str(request.user.id),
            }
        )
        
        return Response({
            'status': 'success',
            'message': 'Sync task queued successfully',
            'task_id': result.id,
            'parameters': {
                'limit': limit,
                'sync_types': sync_types,
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to queue sync task: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to queue sync task', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sync_metrics(request):
    """Get detailed sync metrics and performance data"""
    try:
        restaurant_id = request.user.restaurant_id
        sync_manager = SyncManager()
        
        # Get time range from query params
        days = int(request.GET.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get sync metrics
        metrics = sync_manager.get_sync_metrics(restaurant_id)
        
        # Get historical performance
        historical_data = SyncQueue.objects.filter(
            restaurant_id=restaurant_id,
            created_at__gte=start_date
        ).extra({
            'date': "DATE(created_at)"
        }).values('date', 'sync_type').annotate(
            total=Count('id'),
            successful=Count('id', filter=Q(status='COMPLETED')),
            failed=Count('id', filter=Q(status='FAILED')),
            avg_retry=Avg('retry_count'),
        ).order_by('date', 'sync_type')
        
        # Get current backlog
        backlog = SyncQueue.objects.filter(
            restaurant_id=restaurant_id,
            status__in=['PENDING', 'FAILED']
        ).values('sync_type').annotate(
            count=Count('id'),
            oldest=Min('created_at'),
        )
        
        # Get retry statistics
        retry_stats = SyncQueue.objects.filter(
            restaurant_id=restaurant_id,
            status='FAILED',
            retry_count__gt=0
        ).aggregate(
            avg_retry_count=Avg('retry_count'),
            max_retry_count=Max('retry_count'),
            total_retries=Sum('retry_count'),
        )
        
        return Response({
            'metrics': metrics,
            'historical': historical_data,
            'backlog': backlog,
            'retry_statistics': retry_stats,
            'time_range': {
                'days': days,
                'start_date': start_date,
                'end_date': timezone.now(),
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get sync metrics: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to retrieve sync metrics', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_sync_item(request, sync_id):
    """Cancel a specific sync item"""
    try:
        restaurant_id = request.user.restaurant_id
        
        # Find and cancel the sync item
        sync_item = SyncQueue.objects.get(
            id=sync_id,
            restaurant_id=restaurant_id,
            status__in=['PENDING', 'FAILED', 'CONFLICT']
        )
        
        sync_item.status = 'CANCELLED'
        sync_item.save()
        
        # Log cancellation
        ActivityLog.objects.create(
            restaurant_id=restaurant_id,
            level='INFO',
            module='SYNC_MANAGER',
            action='SYNC_CANCELLED',
            details={
                'sync_id': str(sync_id),
                'sync_type': sync_item.sync_type,
                'cancelled_by': str(request.user.id),
            }
        )
        
        return Response({
            'status': 'success',
            'message': 'Sync item cancelled successfully',
            'sync_id': sync_id,
        })
        
    except SyncQueue.DoesNotExist:
        return Response(
            {'error': 'Sync item not found or cannot be cancelled'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to cancel sync item: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to cancel sync item', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Admin endpoints
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_sync_overview(request):
    """Admin overview of all sync operations"""
    try:
        # Get global statistics
        global_stats = SyncQueue.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            processing=Count('id', filter=Q(status='PROCESSING')),
            completed=Count('id', filter=Q(status='COMPLETED')),
            failed=Count('id', filter=Q(status='FAILED')),
            conflict=Count('id', filter=Q(status='CONFLICT')),
        )
        
        # Get statistics by restaurant
        stats_by_restaurant = SyncQueue.objects.values(
            'restaurant__name', 'restaurant_id'
        ).annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            failed=Count('id', filter=Q(status='FAILED')),
            success_rate=(
                Count('id', filter=Q(status='COMPLETED')) * 100.0 / Count('id')
            ),
        ).order_by('-total')[:20]
        
        # Get recent failures
        recent_failures = SyncQueue.objects.filter(
            status='FAILED',
            updated_at__gte=timezone.now() - timedelta(hours=24)
        ).order_by('-updated_at')[:50]
        
        # Get health check
        health_result = health_check_sync.delay()
        
        return Response({
            'global_statistics': global_stats,
            'by_restaurant': stats_by_restaurant,
            'recent_failures': SyncQueueSerializer(recent_failures, many=True).data,
            'health_check_task': health_result.id,
        })
        
    except Exception as e:
        logger.error(f"Failed to get admin overview: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to retrieve admin overview', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )