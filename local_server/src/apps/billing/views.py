"""
Payment API Views
"""
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.billing.models import Payment, Invoice
from apps.billing.services.payment_processor import payment_processor, crypto_processor

logger = logging.getLogger('dineswift')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Initiate payment processing
    
    POST /api/billing/payments/initiate/
    {
        "invoice_id": "abc-123",
        "payment_type": "MOBILE_MONEY",  // or "BITCOIN", "ETHEREUM", etc.
        "customer_phone": "256700000000",  // For MoMo
        "transaction_hash": "0xabc..."    // For crypto
    }
    """
    try:
        invoice_id = request.data.get('invoice_id')
        payment_type = request.data.get('payment_type')
        
        # Get invoice
        try:
            invoice = Invoice.objects.get(
                id=invoice_id,
                restaurant_id=request.user.restaurant_id
            )
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'Invoice not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create payment record
        payment = Payment.objects.create(
            invoice=invoice,
            restaurant_id=request.user.restaurant_id,
            order=invoice.orders.first() if invoice.orders.exists() else None,
            amount=invoice.amount_due,
            currency=invoice.currency,
            payment_type=payment_type,
            customer_phone=request.data.get('customer_phone'),
            customer_email=request.data.get('customer_email'),
        )
        
        # Process based on payment type
        if payment_type == 'MOBILE_MONEY':
            # Process via Supabase Edge Function
            result = payment_processor.process_momo_payment(payment)
            
        elif payment.is_blockchain_payment():
            # Process crypto payment
            tx_hash = request.data.get('transaction_hash')
            if not tx_hash:
                return Response(
                    {'error': 'transaction_hash required for crypto payments'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            result = crypto_processor.process_crypto_payment(payment, tx_hash)
            
        else:
            return Response(
                {'error': f'Unsupported payment type: {payment_type}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if result.get('success'):
            return Response({
                'success': True,
                'payment_id': str(payment.id),
                'status': payment.status,
                'message': result.get('message'),
                'reference': result.get('reference'),
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'error': result.get('error'),
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Payment initiation error: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Payment initiation failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_payment_status(request, payment_id):
    """
    Check payment status
    
    GET /api/billing/payments/{payment_id}/status/
    """
    try:
        payment = Payment.objects.get(
            id=payment_id,
            restaurant_id=request.user.restaurant_id
        )
        
        # Refresh status from source
        if payment.payment_type == 'MOBILE_MONEY':
            payment_processor.check_payment_status(payment)
            payment.refresh_from_db()
        elif payment.is_blockchain_payment():
            # Blockchain status updated by monitoring task
            pass
        
        return Response({
            'payment_id': str(payment.id),
            'status': payment.status,
            'amount': str(payment.amount),
            'currency': payment.currency,
            'gateway_reference': payment.gateway_reference,
            'transaction_hash': payment.transaction_hash,
            'confirmations': payment.confirmations,
            'completed_at': payment.completed_at.isoformat() if payment.completed_at else None,
        })
        
    except Payment.DoesNotExist:
        return Response(
            {'error': 'Payment not found'},
            status=status.HTTP_404_NOT_FOUND
        )