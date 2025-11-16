from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from ..models import Menu, MenuItem, UserRole
from ..serializers import MenuSerializer, MenuItemCreateSerializer, MenuItemCreateSerializer

@api_view(['GET'])
def get_menu(request, menu_id):
    try:
        menu = Menu.objects.prefetch_related('menuitem_set').get(id=menu_id, is_active=True)
        serializer = MenuSerializer(menu)
        return Response(serializer.data)
    except Menu.DoesNotExist:
        return Response({'error': 'Menu not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_menu_item(request):
    # Check if user is a manager
    try:
        user_role = UserRole.objects.get(
            user=request.user, 
            role__role_name='manager',
            is_active=True
        )
    except UserRole.DoesNotExist:
        return Response(
            {'error': 'Only managers can add menu items'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = MenuItemCreateSerializer(data=request.data)
    if serializer.is_valid():
        # Verify menu belongs to manager's restaurant
        menu = serializer.validated_data['menu']
        if menu.restaurant != user_role.restaurant:
            return Response(
                {'error': 'Cannot add items to menu from different restaurant'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        menu_item = serializer.save()
        return Response(
            {
                'message': 'Menu item added successfully',
                'menu_item_id': menu_item.id,
                'item_name': menu_item.item_name
            }, 
            status=status.HTTP_201_CREATED
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)