import requests
import random
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from .models import LocalMenuCache, OfflineOrder, SyncQueue, LocalServerStatus
from .serializers import *
from .sync import SyncManager

class OfflineOrderViewSet(viewsets.ModelViewSet):
    queryset = OfflineOrder.objects.all()
    serializer_class = OfflineOrderSerializer

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Generate OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        otp_expires = timezone.now() + timedelta(minutes=5)
        
        # Save offline order
        order = serializer.save(
            otp_code=otp_code,
            otp_expires=otp_expires,
            is_synced=False,
            sync_attempts=0,
            last_sync_attempt=timezone.now()
        )
        
        # Add to sync queue with high priority
        SyncQueue.objects.create(
            sync_type='order',
            entity_id=order.local_order_id,
            entity_data=serializer.data,
            status='pending',
            max_retries=5
        )
        
        # Update local server sync status
        self._update_local_server_sync_status()
        
        # Try immediate sync if online
        sync_manager = SyncManager()
        sync_result = sync_manager.sync_orders()
        
        return Response({
            'success': True,
            'local_order_id': str(order.local_order_id),
            'otp_code': otp_code,
            'otp_expires': otp_expires.isoformat(),
            'is_synced': order.is_synced,
            'sync_status': 'pending',
            'immediate_sync_success': sync_result
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def sync_status(self, request):
        """Get sync status for all offline orders"""
        restaurant_id = request.query_params.get('restaurant_id')
        
        if restaurant_id:
            orders = OfflineOrder.objects.filter(restaurant_id=restaurant_id)
        else:
            orders = OfflineOrder.objects.all()
        
        sync_stats = {
            'total_orders': orders.count(),
            'synced_orders': orders.filter(is_synced=True).count(),
            'pending_sync': orders.filter(is_synced=False).count(),
            'failed_syncs': orders.filter(sync_attempts__gte=3, is_synced=False).count(),
        }
        
        # Get recent failed syncs
        recent_failures = orders.filter(
            is_synced=False, 
            sync_attempts__gt=0
        ).order_by('-last_sync_attempt')[:5]
        
        failure_details = []
        for order in recent_failures:
            failure_details.append({
                'local_order_id': str(order.local_order_id),
                'sync_attempts': order.sync_attempts,
                'last_attempt': order.last_sync_attempt,
                'error': order.sync_error
            })
        
        return Response({
            'sync_stats': sync_stats,
            'recent_failures': failure_details
        })

    def _update_local_server_sync_status(self):
        """Update local server sync metrics"""
        try:
            local_server = LocalServerStatus.objects.first()
            if local_server:
                pending_count = SyncQueue.objects.filter(status='pending').count()
                failed_count = SyncQueue.objects.filter(status='failed').count()
                
                local_server.pending_sync_count = pending_count
                local_server.failed_sync_count = failed_count
                local_server.save()
        except Exception as e:
            print(f"Error updating local server status: {e}")

class SyncViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get comprehensive sync dashboard"""
        try:
            local_server = LocalServerStatus.objects.first()
            
            # Sync queue statistics
            sync_queue_stats = {
                'pending': SyncQueue.objects.filter(status='pending').count(),
                'in_progress': SyncQueue.objects.filter(status='in_progress').count(),
                'completed': SyncQueue.objects.filter(status='completed').count(),
                'failed': SyncQueue.objects.filter(status='failed').count(),
                'total': SyncQueue.objects.count(),
            }
            
            # Order sync statistics
            order_sync_stats = {
                'total': OfflineOrder.objects.count(),
                'synced': OfflineOrder.objects.filter(is_synced=True).count(),
                'pending': OfflineOrder.objects.filter(is_synced=False).count(),
            }
            
            # Recent sync activity
            recent_activity = SyncQueue.objects.filter(
                last_attempt__isnull=False
            ).order_by('-last_attempt')[:10]
            
            recent_activity_data = []
            for activity in recent_activity:
                recent_activity_data.append({
                    'sync_type': activity.sync_type,
                    'status': activity.status,
                    'last_attempt': activity.last_attempt,
                    'retry_count': activity.retry_count,
                    'error': activity.error_message
                })
            
            return Response({
                'server_status': {
                    'status': local_server.status if local_server else 'unknown',
                    'last_sync': local_server.last_sync.isoformat() if local_server and local_server.last_sync else None,
                    'last_successful_sync': local_server.last_successful_sync.isoformat() if local_server and local_server.last_successful_sync else None,
                },
                'sync_queue': sync_queue_stats,
                'order_sync': order_sync_stats,
                'recent_activity': recent_activity_data,
                'cloud_connectivity': self._check_cloud_connectivity()
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _check_cloud_connectivity(self):
        """Check connectivity to cloud server"""
        try:
            response = requests.get(f"{settings.CLOUD_SERVER_URL}/api/health/", timeout=5)
            return {
                'status': 'online' if response.status_code == 200 else 'offline',
                'response_time': response.elapsed.total_seconds(),
                'last_checked': timezone.now().isoformat()
            }
        except Exception as e:
            return {
                'status': 'offline',
                'error': str(e),
                'last_checked': timezone.now().isoformat()
            }