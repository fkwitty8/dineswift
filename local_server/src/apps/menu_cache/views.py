import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ViewSet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from .services import menu_cache_service
from .serializers import MenuCacheSerializer, MenuSyncSerializer
from .models import MenuCache

logger = logging.getLogger('dineswift')

@api_view(['GET'])
@permission_classes([AllowAny])
@cache_page(60)  # Cache for 1 minute
def get_current_menu(request):
    """
    Get the current cached menu for a restaurant using query parameters.
    URL Format: /api/menu-cache/current/?restaurant_id=<UUID>&table_number=<INT>
    """
    try:
        # 1. Retrieve required parameters from the query string
        restaurant_id = request.query_params.get('restaurant_id')
        table_number = request.query_params.get('table_number')
        
        # 2. Validation: restaurant_id is mandatory for menu retrieval
        if not restaurant_id:
            return Response(
                {'error': 'A valid restaurant_id is required in the query parameters.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 3. Retrieve menu data using the dedicated service
        # The service layer should handle its own internal caching/DB lookup based on restaurant_id
        menu_data = menu_cache_service.get_cached_menu(restaurant_id)
        
        if not menu_data:
            logger.warning(f"Menu not available for restaurant_id: {restaurant_id}")
            return Response(
                {'error': 'No active menu available for this restaurant. Please check restaurant setup.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 4. Return response including the table_number for order context
        return Response({
            'table_number': table_number, # Captured from QR code link
            'menu': menu_data,
            'cached': True 
        })
        
    except Exception as e:
        logger.error(f"Failed to get current menu for {restaurant_id}: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to retrieve menu due to an internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_menu(request):
    """Sync menu from Supabase"""
    try:
        restaurant_id = request.user.restaurant_id
        
        # You can add parameters like force_refresh via serializer if needed
        success = menu_cache_service.sync_menu_from_supabase(restaurant_id)
        
        if success:
            # Return updated menu
            menu_data = menu_cache_service.get_cached_menu(restaurant_id)
            return Response({
                'status': 'success',
                'message': 'Menu synced successfully',
                'menu': menu_data
            })
        else:
            return Response(
                {'error': 'Failed to sync menu from Supabase'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Menu sync failed: {str(e)}")
        return Response(
            {'error': 'Menu synchronization failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_menu_version(request):
    """Get current menu version info"""
    try:
        restaurant_id = request.user.restaurant_id
        
        version_info = menu_cache_service.get_menu_version(restaurant_id)
        
        if version_info:
            return Response(version_info)
        else:
            return Response(
                {'error': 'No menu version information available'},
                status=status.HTTP_404_NOT_FOUND
            )
            
    except Exception as e:
        logger.error(f"Failed to get menu version: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve menu version'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class MenuCacheViewSet(ViewSet):
    """ViewSet for menu cache operations"""
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get menu cache information"""
        try:
            restaurant_id = request.user.restaurant_id
            
            menu_cache = MenuCache.objects.filter(
                restaurant_id=restaurant_id,
                is_active=True
            ).first()
            
            if not menu_cache:
                return Response(
                    {'detail': 'No active menu cache found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = MenuCacheSerializer(menu_cache)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Menu cache list failed: {str(e)}")
            return Response(
                {'error': 'Failed to retrieve menu cache'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def refresh(self, request):
        """Refresh menu cache"""
        try:
            restaurant_id = request.user.restaurant_id
            
            success = menu_cache_service.sync_menu_from_supabase(restaurant_id)
            
            if success:
                # Return updated menu
                menu_data = menu_cache_service.get_cached_menu(restaurant_id)
                return Response({
                    'status': 'success',
                    'message': 'Menu synced successfully',
                    'menu': menu_data
                })
            else:
                return Response(
                    {'error': 'Failed to sync menu from Supabase'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Menu sync failed: {str(e)}")
            return Response(
                {'error': 'Menu synchronization failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def invalidate(self, request):
        """Invalidate menu cache (force refresh on next request)"""
        try:
            restaurant_id = request.user.restaurant_id
            menu_cache_service.invalidate_cache(restaurant_id)
            
            return Response({
                'status': 'success',
                'message': 'Menu cache invalidated successfully'
            })
            
        except Exception as e:
            logger.error(f"Menu cache invalidation failed: {str(e)}")
            return Response(
                {'error': 'Failed to invalidate cache'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )