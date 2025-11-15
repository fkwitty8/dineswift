from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from .models import Transaction, PaymentMethod, Order, Booking
from .payment_gateways import PaymentGateway
import uuid

@api_view(['POST'])
def validate_payment(request):
    """Validate payment with idempotent transaction handling"""
    data = request.data
    required_fields = ['amount', 'phone', 'provider', 'reference', 'source_entity_id', 'source_entity_type']
    
    if not all(field in data for field in required_fields):
        return Response({'error': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate idempotency key
    gateway = PaymentGateway(data['provider'])
    idempotency_key = gateway.generate_idempotency_key(data)
    
    # Check for existing transaction with same idempotency key
    existing_transaction = Transaction.objects.filter(
        gateway_transaction_id=idempotency_key,
        amount=data['amount'],
        source_entity_id=data['source_entity_id']
    ).first()
    
    if existing_transaction:
        return Response({
            'transaction_id': str(existing_transaction.transaction_id),
            'status': existing_transaction.status,
            'message': 'Transaction already processed'
        })
    
    # Create new transaction with atomic operation
    with transaction.atomic():
        new_transaction = Transaction.objects.create(
            restaurant_id=data.get('restaurant_id'),
            source_entity_id=data['source_entity_id'],
            source_entity_type=data['source_entity_type'],
            amount=data['amount'],
            transaction_type='payment',
            category=data.get('category', 'order'),
            gateway_transaction_id=idempotency_key,
            status='pending',
            transaction_date=timezone.now(),
            notes=f"Payment via {data['provider']} - {data['phone']}"
        )
        
        # Validate with payment gateway
        is_valid = gateway.validate_transaction(
            str(new_transaction.transaction_id),
            data['amount'],
            data['phone']
        )
        
        if is_valid:
            new_transaction.status = 'completed'
            new_transaction.save()
            
            # Update source entity status
            _update_source_entity_status(data['source_entity_type'], data['source_entity_id'], 'paid')
            
            return Response({
                'transaction_id': str(new_transaction.transaction_id),
                'status': 'completed',
                'message': 'Payment validated successfully',
                'amount': str(new_transaction.amount),
                'provider': data['provider']
            })
        else:
            new_transaction.status = 'failed'
            new_transaction.save()
            
            return Response({
                'transaction_id': str(new_transaction.transaction_id),
                'status': 'failed',
                'message': 'Payment validation failed'
            }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def verify_transaction(request):
    """Verify existing transaction status"""
    transaction_id = request.data.get('transaction_id')
    
    if not transaction_id:
        return Response({'error': 'transaction_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        txn = Transaction.objects.get(transaction_id=transaction_id)
        return Response({
            'transaction_id': str(txn.transaction_id),
            'status': txn.status,
            'amount': str(txn.amount),
            'transaction_date': txn.transaction_date,
            'source_entity_type': txn.source_entity_type,
            'source_entity_id': str(txn.source_entity_id)
        })
    except Transaction.DoesNotExist:
        return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

def _update_source_entity_status(entity_type, entity_id, payment_status):
    """Update payment status of source entity"""
    if entity_type == 'order':
        try:
            order = Order.objects.get(id=entity_id)
            if payment_status == 'paid':
                order.status = 'confirmed'
                order.save()
        except Order.DoesNotExist:
            pass
    elif entity_type == 'booking':
        try:
            booking = Booking.objects.get(id=entity_id)
            if payment_status == 'paid':
                booking.deposit_status = 'paid'
                booking.status = 'confirmed'
                booking.save()
        except Booking.DoesNotExist:
            pass