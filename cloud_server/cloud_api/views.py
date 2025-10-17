from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from .models import Restaurant, Menu, MenuItem, RestaurantTable, Booking, Order, SalesOrder, OrderItem
from .serializers import *

class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.filter(status='active')
    serializer_class = RestaurantSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['cuisine_type', 'halal_status']
    search_fields = ['name', 'description', 'cuisine_type']
    ordering_fields = ['average_rating', 'total_reviews', 'average_delivery_time', 'name']
    
    @action(detail=False, methods=['get'])
    def halal_restaurants(self, request):
        """Get all halal certified restaurants"""
        halal_restaurants = Restaurant.objects.filter(
            status='active',
            halal_status__in=['halal', 'halal_options']
        ).order_by('-average_rating')
        
        page = self.paginate_queryset(halal_restaurants)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(halal_restaurants, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_cuisine(self, request):
        """Get restaurants by cuisine with halal filter"""
        cuisine = request.query_params.get('cuisine')
        halal_only = request.query_params.get('halal_only', 'false').lower() == 'true'
        
        queryset = Restaurant.objects.filter(status='active')
        
        if cuisine:
            queryset = queryset.filter(cuisine_type__icontains=cuisine)
        
        if halal_only:
            queryset = queryset.filter(halal_status__in=['halal', 'halal_options'])
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class MenuViewSet(viewsets.ModelViewSet):
    queryset = Menu.objects.filter(is_active=True)
    serializer_class = MenuSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['restaurant']

    def get_queryset(self):
        queryset = Menu.objects.filter(is_active=True)
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        return queryset

class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.filter(is_available=True)
    serializer_class = MenuItemSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['menu', 'is_halal', 'department']
    search_fields = ['item_name', 'description']
    
    @action(detail=False, methods=['get'])
    def halal_items(self, request):
        """Get all halal menu items for a restaurant"""
        restaurant_id = request.query_params.get('restaurant_id')
        if not restaurant_id:
            return Response({'error': 'restaurant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            menu = Menu.objects.get(restaurant_id=restaurant_id, is_active=True)
            halal_items = MenuItem.objects.filter(
                menu=menu,
                is_available=True,
                is_halal=True
            ).order_by('display_order')
            
            serializer = self.get_serializer(halal_items, many=True)
            return Response(serializer.data)
        except Menu.DoesNotExist:
            return Response({'error': 'Menu not found'}, status=status.HTTP_404_NOT_FOUND)

class QRCodeViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    def resolve(self, request):
        qr_code = request.data.get('qr_code')
        
        try:
            table = RestaurantTable.objects.select_related('restaurant').get(qr_code=qr_code)
            restaurant = table.restaurant
            
            # Get active menu
            menu = Menu.objects.filter(restaurant=restaurant, is_active=True).first()
            menu_items = MenuItem.objects.filter(menu=menu, is_available=True).order_by('display_order')
            
            menu_data = MenuSerializer(menu).data
            menu_data['items'] = MenuItemSerializer(menu_items, many=True).data
            
            return Response({
                'success': True,
                'table': {
                    'table_id': str(table.table_id),
                    'table_number': table.table_number,
                    'capacity': table.capacity
                },
                'restaurant': {
                    'restaurant_id': str(restaurant.restaurant_id),
                    'name': restaurant.name,
                    'cuisine_type': restaurant.cuisine_type,
                    'logo_url': restaurant.logo.url if restaurant.logo else restaurant.logo_url,
                    'halal_status': restaurant.halal_status,
                    'halal_status_display': restaurant.get_halal_status_display(),
                },
                'menu': menu_data
            })
            
        except RestaurantTable.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Invalid QR code'
            }, status=status.HTTP_404_NOT_FOUND)