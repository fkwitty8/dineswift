from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import RestaurantTable, Menu
from .serializers import MenuSerializer

@api_view(['POST'])
def resolve_qr_code(request):
    qr_code = request.data.get('qr_code')
    
    if not qr_code:
        return Response({'error': 'QR code required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        table = RestaurantTable.objects.select_related('restaurant').get(qr_code=qr_code)
        
        if table.table_status != 'available':
            return Response({
                'error': 'Table not available',
                'table_status': table.table_status
            }, status=status.HTTP_403_FORBIDDEN)
        
        menu = Menu.objects.get(restaurant=table.restaurant, is_active=True)
        
        # Generate restaurant-specific URL with table mapping
        base_url = request.build_absolute_uri('/')[:-1]  # Remove trailing slash
        restaurant_url = f"{base_url}/restaurant/{table.restaurant.id}/table/{table.id}"
        menu_url = f"{base_url}/api/restaurant/{table.restaurant.id}/menu/"
        
        return Response({
            'success': True,
            'restaurant_url': restaurant_url,
            'menu_url': menu_url,
            'table_mapping': {
                'table_id': str(table.id),
                'table_number': table.table_number,
                'capacity': table.capacity,
                'restaurant_id': str(table.restaurant.id),
                'restaurant_name': table.restaurant.name
            },
            'menu_id': str(menu.id)
        })
        
    except RestaurantTable.DoesNotExist:
        return Response({'error': 'Invalid QR code'}, status=status.HTTP_404_NOT_FOUND)
    except Menu.DoesNotExist:
        return Response({'error': 'Menu not available'}, status=status.HTTP_404_NOT_FOUND)