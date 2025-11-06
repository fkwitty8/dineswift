import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .services import OTPService
from .serializers import OTPGenerateSerializer, OTPVerifySerializer
from .models import OTP

logger = logging.getLogger('dineswift')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_otp(request):
    """Generate OTP for an order"""
    try:
        serializer = OTPGenerateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        service = OTPService()
        result = service.generate_otp(serializer.validated_data['order_id'])
        
        return Response({
            'success': True,
            'otp_code': result['otp_code'],
            'expires_at': result['expires_at'],
            'otp_id': result['otp_id']
        })
        
    except Exception as e:
        logger.error(f"OTP generation failed: {str(e)}")
        return Response(
            {'error': 'Failed to generate OTP'},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_otp(request):
    """Verify OTP for order pickup"""
    try:
        serializer = OTPVerifySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        service = OTPService()
        result = service.verify_otp(
            serializer.validated_data['order_id'],
            serializer.validated_data['otp_code']
        )
        
        return Response(result)
        
    except Exception as e:
        logger.error(f"OTP verification failed: {str(e)}")
        return Response(
            {'error': 'OTP verification failed'},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_otp(request, order_id):
    """Get OTP information for an order"""
    try:
        # Verify the order belongs to the restaurant
        from apps.order_processing.models import OfflineOrder
        
        order = OfflineOrder.objects.get(
            id=order_id,
            restaurant_id=request.user.restaurant_id
        )
        
        # Get active OTP for this order
        otp = OTP.objects.filter(
            order_id=order_id,
            status='ACTIVE'
        ).first()
        
        if not otp:
            return Response(
                {'error': 'No active OTP found for this order'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        from .serializers import OTPSerializer
        serializer = OTPSerializer(otp)
        return Response(serializer.data)
        
    except OfflineOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to get order OTP: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve OTP information'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )