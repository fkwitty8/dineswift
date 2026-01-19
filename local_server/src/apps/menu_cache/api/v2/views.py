"""
V2 Views - Uses ModernMenuService for Flutter app
"""
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.viewsets import ViewSet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from apps.menu_cache.services.modern_services import modern_menu_service
from .serializers import MenuCacheV2Serializer, MenuSyncV2Serializer
from apps.menu_cache.models import MenuCache

logger = logging.getLogger('dineswift')

@api_view(['GET'])
@permission_classes([AllowAny])
@cache_page(30)  # Shorter cache for more real-time updates
def get_current_menu(request):
    """
    Get current menu for Flutter app with enhanced features
    UC-FLUTTER-001: Display interactive menu
    """
    try:
        restaurant_id = request.query_params.get('restaurant_id')
        table_number = request.query_params.get('table_number')
        session_id = request.query_params.get('session_id')
        
        if not restaurant_id:
            return Response(
                {'error': 'restaurant_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Enhanced menu retrieval with Flutter optimizations
        menu_data = modern_menu_service.get_menu_for_flutter(
            restaurant_id,
            include_customizations=True,
            include_dietary_info=True
        )
        
        if not menu_data:
            return Response(
                {
                    'status': 'error',
                    'code': 'MENU_NOT_AVAILABLE',
                    'message': 'No active menu found for this restaurant',
                    'suggestions': ['Try refreshing', 'Contact restaurant staff']
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Add Flutter-specific metadata
        response_data = {
            'status': 'success',
            'api_version': '2.0',
            'session_id': session_id,
            'table_context': {
                'table_number': table_number,
                'session_active': bool(session_id)
            },
            'menu': menu_data['menu'],
            'metadata': menu_data.get('metadata', {}),
            'features': {
                'supports_customizations': True,
                'supports_dietary_filters': True,
                'supports_real_time_updates': True,
                'supports_images': True
            },
            'cache_info': {
                'cached': menu_data.get('cached', False),
                'freshness': menu_data.get('freshness', 'unknown')
            }
        }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"V2: Failed to get menu: {str(e)}", exc_info=True)
        return Response(
            {
                'status': 'error',
                'code': 'SERVER_ERROR',
                'message': 'Failed to retrieve menu'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_menu(request):
    """Sync menu with enhanced features for Flutter"""
    try:
        serializer = MenuSyncV2Serializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        success = modern_menu_service.sync_menu_with_enhancements(
            str(data['restaurant_id']),
            force_refresh=data.get('force_refresh', False)
        )
        
        if success:
            menu_data = modern_menu_service.get_menu_for_flutter(
                str(data['restaurant_id']),
                include_metadata=data.get('include_metadata', True)
            )
            return Response({
                'status': 'success',
                'message': 'Menu synchronized successfully',
                'data': menu_data,
                'sync_details': {
                    'timestamp': modern_menu_service.get_last_sync_time(str(data['restaurant_id'])),
                    'items_updated': menu_data.get('metadata', {}).get('items_count', 0)
                }
            })
        else:
            return Response({
                'status': 'error',
                'code': 'SYNC_FAILED',
                'message': 'Failed to synchronize menu'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"V2: Menu sync failed: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'code': 'INTERNAL_ERROR'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ModernMenuCacheViewSet(ViewSet):
    """ViewSet for modern menu cache operations with Flutter optimizations"""
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get menu cache with enhanced information"""
        try:
            restaurant_id = request.user.restaurant_id
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_id,
                is_active=True
            ).first()
            
            if not menu_cache:
                return Response({
                    'status': 'error',
                    'code': 'NO_CACHE'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = MenuCacheV2Serializer(menu_cache)
            
            # Add service layer insights
            insights = modern_menu_service.get_cache_insights(str(restaurant_id))
            
            response_data = {
                'status': 'success',
                'cache': serializer.data,
                'insights': insights,
                'performance': {
                    'cache_hit_rate': modern_menu_service.get_cache_hit_rate(str(restaurant_id)),
                    'avg_load_time': modern_menu_service.get_average_load_time(str(restaurant_id))
                }
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"V2: Cache list failed: {str(e)}")
            return Response({
                'status': 'error',
                'code': 'INTERNAL_ERROR'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def refresh(self, request):
        """Enhanced refresh with progress tracking"""
        try:
            restaurant_id = request.user.restaurant_id
            
            # Async refresh with progress tracking
            refresh_id = modern_menu_service.start_async_refresh(str(restaurant_id))
            
            return Response({
                'status': 'success',
                'message': 'Menu refresh started',
                'refresh_id': refresh_id,
                'progress_url': f'/api/menu-cache/v2/refresh-status/{refresh_id}/'
            })
            
        except Exception as e:
            logger.error(f"V2: Refresh failed: {str(e)}")
            return Response({
                'status': 'error',
                'code': 'REFRESH_FAILED'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def preload(self, request):
        """Preload menu for better UX"""
        try:
            restaurant_id = request.user.restaurant_id
            success = modern_menu_service.preload_menu(str(restaurant_id))
            
            if success:
                return Response({
                    'status': 'success',
                    'message': 'Menu preloaded successfully'
                })
            else:
                return Response({
                    'status': 'error',
                    'code': 'PRELOAD_FAILED'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"V2: Preload failed: {str(e)}")
            return Response({
                'status': 'error',
                'code': 'INTERNAL_ERROR'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)