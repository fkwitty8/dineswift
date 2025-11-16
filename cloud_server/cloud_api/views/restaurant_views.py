from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Restaurant, Menu, RestaurantTable
from ..serializers import MenuSerializer

@api_view(['GET'])
def restaurant_menu(request, restaurant_id):
    try:
        restaurant = Restaurant.objects.get(id=restaurant_id, status='active')
        menu = Menu.objects.prefetch_related('menuitem_set').get(restaurant=restaurant, is_active=True)
        serializer = MenuSerializer(menu)
        return Response({
            'restaurant': {
                'id': str(restaurant.id),
                'name': restaurant.name,
                'description': restaurant.description
            },
            'menu': serializer.data
        })
    except (Restaurant.DoesNotExist, Menu.DoesNotExist):
        return Response({'error': 'Restaurant or menu not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def restaurant_table_info(request, restaurant_id, table_id):
    try:
        table = RestaurantTable.objects.select_related('restaurant').get(
            id=table_id, 
            restaurant_id=restaurant_id
        )
        return Response({
            'table': {
                'id': str(table.id),
                'number': table.table_number,
                'capacity': table.capacity,
                'status': table.table_status
            },
            'restaurant': {
                'id': str(table.restaurant.id),
                'name': table.restaurant.name
            }
        })
    except RestaurantTable.DoesNotExist:
        return Response({'error': 'Table not found'}, status=status.HTTP_404_NOT_FOUND)