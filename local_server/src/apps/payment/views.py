import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .services import PaymentService
from .serializers import PaymentInitiateSerializer, PaymentWebhookSerializer

logger = logging.getLogger('dineswift')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """Initiate payment for an order"""
    try:
        serializer = PaymentInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        result = service.initiate_payment(
            order_data=serializer.validated_data,
            restaurant_id=request.user.restaurant_id
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {'error': result.get('error', 'Payment initiation failed')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Payment initiation failed: {str(e)}")
        return Response(
            {'error': 'Payment initiation failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_payment_status(request, payment_id):
    """Get payment status"""
    try:
        service = PaymentService()
        status_info = service.get_payment_status(payment_id)
        
        return Response(status_info)
        
    except Exception as e:
        logger.error(f"Failed to get payment status: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve payment status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_payment(request, order_id):
    """Get payment information for an order"""
    try:
        # Verify order belongs to restaurant
        from apps.order_processing.models import OfflineOrder
        
        order = OfflineOrder.objects.get(
            id=order_id,
            restaurant_id=request.user.restaurant_id
        )
        
        service = PaymentService()
        
        if not order.payment_id:
            return Response(
                {'error': 'No payment found for this order'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        status_info = service.get_payment_status(order.payment_id)
        
        return Response({
            'order_id': order_id,
            'payment': status_info
        })
        
    except OfflineOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to get order payment: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve payment information'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([])  # No authentication for webhooks
def momo_webhook(request):
    """Handle Momo payment webhook"""
    try:
        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        result = service.handle_webhook(serializer.validated_data)
        
        if result['success']:
            return Response({'status': 'success'})
        else:
            logger.error(f"Webhook handling failed: {result.get('error')}")
            return Response(
                {'error': result.get('error')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}")
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )