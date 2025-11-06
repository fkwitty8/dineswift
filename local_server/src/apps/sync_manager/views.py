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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sync_status(request):
    """Get synchronization status for the restaurant"""
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
            conflict=Count('id', filter=Q(status='CONFLICT'))
        )
        
        # Get recent sync activities
        recent_activities = SyncQueue.objects.filter(
            restaurant_id=restaurant_id
        ).order_by('-created_at')[:10]
        
        serializer = SyncQueueSerializer(recent_activities, many=True)
        
        return Response({
            'statistics': stats,
            'recent_activities': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Failed to get sync status: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve sync status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sync_queue(request):
    """Get current sync queue items"""
    try:
        restaurant_id = request.user.restaurant_id
        
        status_filter = request.GET.get('status', 'PENDING')
        limit = int(request.GET.get('limit', 50))
        
        queue_items = SyncQueue.objects.filter(
            restaurant_id=restaurant_id,
            status=status_filter
        ).order_by('priority', 'created_at')[:limit]
        
        serializer = SyncQueueSerializer(queue_items, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Failed to get sync queue: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve sync queue'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def retry_failed_syncs(request):
    """Manually retry failed sync operations"""
    try:
        # Trigger the retry task
        result = retry_failed_syncs.delay()
        
        return Response({
            'status': 'success',
            'message': 'Retry task queued successfully',
            'task_id': result.id
        })
        
    except Exception as e:
        logger.error(f"Failed to queue retry task: {str(e)}")
        return Response(
            {'error': 'Failed to queue retry task'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def force_sync(request):
    """Force immediate synchronization"""
    try:
        # Trigger sync task immediately
        result = sync_pending_orders.delay()
        
        return Response({
            'status': 'success',
            'message': 'Sync task queued successfully',
            'task_id': result.id
        })
        
    except Exception as e:
        logger.error(f"Failed to queue sync task: {str(e)}")
        return Response(
            {'error': 'Failed to queue sync task'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )