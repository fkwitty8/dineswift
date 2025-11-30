import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .services import invoice_service, payment_service, wallet_service
from .serializers import (
    # Invoice
    InvoiceCreateSerializer,
    InvoiceStatusSerializer,
    
    # Payment
    PaymentInitiateSerializer,
    PaymentStatusSerializer,
    PaymentAllocationCreateSerializer,
    RefundRequestSerializer,
    OrderPaymentsSerializer,
    
    # Wallet
    WalletBalanceSerializer,
    AddFundsSerializer,
    WalletTransactionSerializer,
    
    # Webhook
    PaymentWebhookSerializer,
)

logger = logging.getLogger('dineswift')

# =============================================================================
# INVOICE VIEWS
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_invoice(request):
    """Create invoice for an order"""
    try:
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = invoice_service.create_invoice(
            order_id=serializer.validated_data['order_id'],
            restaurant_id=request.user.restaurant_id,
            amount=serializer.validated_data['amount'],
            tax_amount=serializer.validated_data.get('tax_amount', 0),
            service_fee=serializer.validated_data.get('service_fee', 0),
            discount_amount=serializer.validated_data.get('discount_amount', 0),
            currency=serializer.validated_data.get('currency', 'UGX'),
            due_date=serializer.validated_data.get('due_date'),
            user_id=str(request.user.id)
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {'error': result.get('error', 'Invoice creation failed')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Invoice creation failed: {str(e)}")
        return Response(
            {'error': 'Invoice creation failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_invoice_status(request, invoice_id):
    """Get invoice status and payment allocations"""
    try:
        status_info = invoice_service.get_invoice_status(
            invoice_id=invoice_id,
            user_id=str(request.user.id)
        )
        
        if 'error' in status_info:
            return Response(
                {'error': status_info['error']},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(status_info)
        
    except Exception as e:
        logger.error(f"Failed to get invoice status: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve invoice status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_invoice(request, order_id):
    """Get invoice for a specific order"""
    try:
        # Verify order belongs to restaurant
        from apps.order_processing.models import OfflineOrder
        
        order = OfflineOrder.objects.get(
            id=order_id,
            restaurant_id=request.user.restaurant_id
        )
        
        invoice_info = invoice_service.get_order_invoice(str(order_id))
        
        if 'error' in invoice_info:
            return Response(
                {'error': invoice_info['error']},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(invoice_info)
        
    except OfflineOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to get order invoice: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve invoice information'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# PAYMENT VIEWS
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """Initiate payment for an invoice"""
    try:
        serializer = PaymentInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Add user context for logging and processing
        payment_data = serializer.validated_data.copy()
        payment_data['user_id'] = str(request.user.id)
        payment_data['restaurant_id'] = str(request.user.restaurant_id)
        
        result = payment_service.initiate_payment(
            payment_data=payment_data,
            user_id=str(request.user.id)
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
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
    """Get detailed payment status with allocations"""
    try:
        status_info = payment_service.get_payment_status(
            payment_id=payment_id,
            user_id=str(request.user.id)
        )
        
        if 'error' in status_info:
            return Response(
                {'error': status_info['error']},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(status_info)
        
    except Exception as e:
        logger.error(f"Failed to get payment status: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve payment status'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def allocate_payment(request, payment_id):
    """Manually allocate payment to invoice"""
    try:
        serializer = PaymentAllocationCreateSerializer(data={
            **request.data,
            'payment_id': payment_id
        })
        serializer.is_valid(raise_exception=True)
        
        result = payment_service.allocate_payment(
            payment_id=payment_id,
            invoice_id=serializer.validated_data['invoice_id'],
            amount=serializer.validated_data['amount'],
            user_id=str(request.user.id)
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result.get('error', 'Payment allocation failed')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Payment allocation failed: {str(e)}")
        return Response(
            {'error': 'Payment allocation failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_refund(request, payment_id):
    """Request refund for a payment"""
    try:
        serializer = RefundRequestSerializer(data={
            **request.data,
            'payment_id': payment_id
        })
        serializer.is_valid(raise_exception=True)
        
        result = payment_service.process_refund(
            payment_id=payment_id,
            amount=serializer.validated_data['amount'],
            reason=serializer.validated_data['reason'],
            refund_to_original_method=serializer.validated_data.get('refund_to_original_method', True),
            alternative_method_id=serializer.validated_data.get('alternative_method_id'),
            user_id=str(request.user.id)
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result.get('error', 'Refund request failed')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Refund request failed: {str(e)}")
        return Response(
            {'error': 'Refund request failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_order_payments(request, order_id):
    """Get all payments and allocations for an order"""
    try:
        # Verify order belongs to restaurant
        from apps.order_processing.models import OfflineOrder
        
        order = OfflineOrder.objects.get(
            id=order_id,
            restaurant_id=request.user.restaurant_id
        )
        
        payments_info = payment_service.get_order_payments_summary(str(order_id))
        
        if 'error' in payments_info:
            return Response(
                {'error': payments_info['error']},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(payments_info)
        
    except OfflineOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to get order payments: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve payment information'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# WALLET VIEWS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_balance(request):
    """Get customer wallet balance"""
    try:
        balance_info = wallet_service.get_wallet_balance(
            user_id=str(request.user.id),
            restaurant_id=request.user.restaurant_id
        )
        
        if 'error' in balance_info:
            return Response(
                {'error': balance_info['error']},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(balance_info)
        
    except Exception as e:
        logger.error(f"Failed to get wallet balance: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve wallet balance'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_transactions(request):
    """Get wallet transaction history"""
    try:
        # Optional query parameters for filtering
        page = request.GET.get('page', 1)
        limit = request.GET.get('limit', 50)
        transaction_type = request.GET.get('transaction_type')
        
        transactions_info = wallet_service.get_wallet_transactions(
            user_id=str(request.user.id),
            restaurant_id=request.user.restaurant_id,
            page=int(page),
            limit=int(limit),
            transaction_type=transaction_type
        )
        
        if 'error' in transactions_info:
            return Response(
                {'error': transactions_info['error']},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(transactions_info)
        
    except Exception as e:
        logger.error(f"Failed to get wallet transactions: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve wallet transactions'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_wallet_funds(request):
    """Add funds to customer wallet"""
    try:
        serializer = AddFundsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = wallet_service.add_funds(
            user_id=str(request.user.id),
            restaurant_id=request.user.restaurant_id,
            amount=serializer.validated_data['amount'],
            reference_type=serializer.validated_data['reference_type'],
            reference_id=serializer.validated_data.get('reference_id'),
            description=serializer.validated_data['description']
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': result.get('error', 'Failed to add funds')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Failed to add wallet funds: {str(e)}")
        return Response(
            {'error': 'Failed to add funds to wallet'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_payment_methods(request):
    """Get user's payment methods"""
    try:
        payment_methods = wallet_service.get_user_payment_methods(
            user_id=str(request.user.id)
        )
        
        return Response({
            'success': True,
            'payment_methods': payment_methods
        })
        
    except Exception as e:
        logger.error(f"Failed to get payment methods: {str(e)}")
        return Response(
            {'error': 'Failed to retrieve payment methods'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# WEBHOOK VIEWS (No authentication required)
# =============================================================================

@api_view(['POST'])
@permission_classes([])
def momo_webhook(request):
    """Handle Momo payment webhook"""
    try:
        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = payment_service.handle_webhook(
            webhook_data=serializer.validated_data,
            gateway='MOMO'
        )
        
        if result['success']:
            return Response({'status': 'success'})
        else:
            logger.error(f"Momo webhook handling failed: {result.get('error')}")
            return Response(
                {'error': result.get('error')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Momo webhook processing failed: {str(e)}")
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def card_webhook(request):
    """Handle card payment webhook"""
    try:
        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        result = payment_service.handle_webhook(
            webhook_data=serializer.validated_data,
            gateway='CARD'
        )
        
        if result['success']:
            return Response({'status': 'success'})
        else:
            logger.error(f"Card webhook handling failed: {result.get('error')}")
            return Response(
                {'error': result.get('error')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Card webhook processing failed: {str(e)}")
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def generic_payment_webhook(request):
    """Handle generic payment webhook for multiple gateways"""
    try:
        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract gateway from headers or request data
        gateway = request.META.get('HTTP_X_GATEWAY') or request.data.get('gateway')
        
        if not gateway:
            return Response(
                {'error': 'Payment gateway not specified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = payment_service.handle_webhook(
            webhook_data=serializer.validated_data,
            gateway=gateway.upper()
        )
        
        if result['success']:
            return Response({'status': 'success'})
        else:
            logger.error(f"Generic webhook handling failed: {result.get('error')}")
            return Response(
                {'error': result.get('error')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Generic webhook processing failed: {str(e)}")
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )