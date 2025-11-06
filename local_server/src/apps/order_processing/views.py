#Mobile App API Endpoints

from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend

from .models import OfflineOrder
from .serializer import (
    OrderCreateSerializer, OrderSerializer, OrderStatusUpdateSerializer,
    OrderWithPaymentSerializer
)
from .services import OrderProcessingService

class OrderViewSet(ModelViewSet):
    """ViewSet for order operations"""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['order_status', 'sync_status']
    
    def get_queryset(self):
        return OfflineOrder.objects.filter(
            restaurant_id=self.request.user.restaurant_id
        ).select_related('restaurant').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action == 'update_status':
            return OrderStatusUpdateSerializer
        return OrderSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new order with validation"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderProcessingService()
        result = service.create_offline_order(
            restaurant_id=request.user.restaurant_id,
            order_data=serializer.validated_data
        )
        
        if result['success']:
            # Return the created order
            order = OfflineOrder.objects.get(id=result['order_id'])
            response_serializer = OrderSerializer(order)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {'error': result.get('error', 'Order creation failed')},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status"""
        order = self.get_object()
        serializer = self.get_serializer(order, data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderProcessingService()
        success = service.update_order_status(
            order_id=order.id,
            new_status=serializer.validated_data['status'],
            notes=serializer.validated_data.get('notes', '')
        )
        
        if success:
            order.refresh_from_db()
            response_serializer = OrderSerializer(order)
            return Response(response_serializer.data)
        else:
            return Response(
                {'error': 'Failed to update order status'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def with_payment(self, request, pk=None):
        """Get order with payment status"""
        order = self.get_object()
        
        # Get payment status if exists
        payment_status = {}
        if hasattr(order, 'payment') and order.payment:
            from apps.payment.serializers import PaymentStatusSerializer
            payment_status = PaymentStatusSerializer(order.payment).data
        
        serializer = OrderWithPaymentSerializer({
            'order': order,
            'payment': payment_status
        })
        return Response(serializer.data)

