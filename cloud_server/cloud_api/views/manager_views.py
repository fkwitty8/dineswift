from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from ..models import Menu, MenuItem, Restaurant, UserRole
from ..serializers import MenuSerializer, MenuItemSerializer, MenuWithItemsSerializer

class ManagerPermissionMixin:
    def check_manager_permission(self, restaurant_id):
        user_role = UserRole.objects.filter(
            user=self.request.user,
            restaurant_id=restaurant_id,
            role__role_name='manager',
            is_active=True
        ).first()
        return user_role is not None

class MenuManagerViewSet(ManagerPermissionMixin, viewsets.ModelViewSet):
    serializer_class = MenuSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id and self.check_manager_permission(restaurant_id):
            return Menu.objects.filter(restaurant_id=restaurant_id)
        return Menu.objects.none()
    
    def perform_create(self, serializer):
        restaurant_id = serializer.validated_data['restaurant'].id
        if not self.check_manager_permission(restaurant_id):
            raise PermissionError("Only managers can create menus")
        serializer.save()
    
    def perform_update(self, serializer):
        restaurant_id = serializer.instance.restaurant.id
        if not self.check_manager_permission(restaurant_id):
            raise PermissionError("Only managers can update menus")
        serializer.save()
    
    def perform_destroy(self, instance):
        if not self.check_manager_permission(instance.restaurant.id):
            raise PermissionError("Only managers can delete menus")
        instance.delete()
    
    @action(detail=True, methods=['get'])
    def with_items(self, request, pk=None):
        menu = self.get_object()
        if not self.check_manager_permission(menu.restaurant.id):
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        serializer = MenuWithItemsSerializer(menu)
        return Response(serializer.data)

class MenuItemManagerViewSet(ManagerPermissionMixin, viewsets.ModelViewSet):
    serializer_class = MenuItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        menu_id = self.request.query_params.get('menu_id')
        if menu_id:
            menu = get_object_or_404(Menu, id=menu_id)
            if self.check_manager_permission(menu.restaurant.id):
                return MenuItem.objects.filter(menu_id=menu_id)
        return MenuItem.objects.none()
    
    def perform_create(self, serializer):
        menu = serializer.validated_data['menu']
        if not self.check_manager_permission(menu.restaurant.id):
            raise PermissionError("Only managers can create menu items")
        serializer.save()
    
    def perform_update(self, serializer):
        menu = serializer.instance.menu
        if not self.check_manager_permission(menu.restaurant.id):
            raise PermissionError("Only managers can update menu items")
        serializer.save()
    
    def perform_destroy(self, instance):
        if not self.check_manager_permission(instance.menu.restaurant.id):
            raise PermissionError("Only managers can delete menu items")
        instance.delete()