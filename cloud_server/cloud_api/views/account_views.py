from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from ..models import CustomerAccount, Transaction, Order, Booking
from ..serializers.account_serializers import CustomerAccountSerializer, DepositSerializer, WithdrawSerializer
from ..utils.payment_gateways import PaymentGateway
from decimal import Decimal

class CustomerAccountViewSet(viewsets.ModelViewSet):
    queryset = CustomerAccount.objects.all()
    serializer_class = CustomerAccountSerializer
    
    def get_queryset(self):
        queryset = CustomerAccount.objects.select_related('restaurant', 'user')
        user_id = self.request.query_params.get('user_id')
        restaurant_id = self.request.query_params.get('restaurant_id')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def deposit(self, request, pk=None):
        """Process deposit payment to customer account"""
        account = self.get_object()
        serializer = DepositSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        # Validate payment with gateway
        gateway = PaymentGateway(data['provider'])
        idempotency_key = gateway.generate_idempotency_key({
            'amount': data['amount'],
            'phone': data['phone'],
            'reference': data['reference']
        })
        
        # Check for duplicate transaction
        existing_txn = Transaction.objects.filter(
            gateway_transaction_id=idempotency_key,
            source_entity_id=account.account_id,
            transaction_type='deposit'
        ).first()
        
        if existing_txn:
            return Response({
                'message': 'Deposit already processed',
                'transaction_id': str(existing_txn.transaction_id),
                'status': existing_txn.status
            })
        
        # Process deposit with atomic transaction
        with transaction.atomic():
            # Create transaction record
            txn = Transaction.objects.create(
                restaurant=account.restaurant,
                source_entity_id=account.account_id,
                source_entity_type='customer_account',
                amount=data['amount'],
                transaction_type='deposit',
                category='account',
                gateway_transaction_id=idempotency_key,
                status='pending',
                transaction_date=timezone.now(),
                notes=f"Account deposit via {data['provider']} - {data['phone']}"
            )
            
            # Validate with payment gateway
            is_valid = gateway.validate_transaction(
                str(txn.transaction_id),
                data['amount'],
                data['phone']
            )
            
            if is_valid:
                # Update account balance
                account.balance += data['amount']
                account.save()
                
                txn.status = 'completed'
                txn.save()
                
                return Response({
                    'message': 'Deposit successful',
                    'transaction_id': str(txn.transaction_id),
                    'new_balance': str(account.balance),
                    'amount_deposited': str(data['amount'])
                })
            else:
                txn.status = 'failed'
                txn.save()
                
                return Response({
                    'message': 'Deposit failed - payment validation failed',
                    'transaction_id': str(txn.transaction_id)
                }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        """Withdraw money from customer account (refund)"""
        account = self.get_object()
        serializer = WithdrawSerializer(data=request.data, context={'account': account})
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        if not account.is_refundable:
            return Response({'error': 'Account is not refundable'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Create withdrawal transaction
            txn = Transaction.objects.create(
                restaurant=account.restaurant,
                source_entity_id=account.account_id,
                source_entity_type='customer_account',
                amount=-data['amount'],  # Negative for withdrawal
                transaction_type='withdrawal',
                category='account',
                status='completed',
                transaction_date=timezone.now(),
                notes=f"Account withdrawal: {data.get('reason', 'Customer request')}"
            )
            
            # Update account balance
            account.balance -= data['amount']
            account.save()
            
            return Response({
                'message': 'Withdrawal successful',
                'transaction_id': str(txn.transaction_id),
                'new_balance': str(account.balance),
                'amount_withdrawn': str(data['amount'])
            })
    
    @action(detail=True, methods=['post'])
    def pay_from_account(self, request, pk=None):
        """Pay for order/booking using account balance"""
        account = self.get_object()
        amount = Decimal(request.data.get('amount', '0'))
        source_entity_id = request.data.get('source_entity_id')
        source_entity_type = request.data.get('source_entity_type')  # 'order' or 'booking'
        
        if amount <= 0:
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
        
        if account.balance < amount:
            return Response({
                'error': 'Insufficient balance',
                'current_balance': str(account.balance),
                'required_amount': str(amount)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Create payment transaction
            txn = Transaction.objects.create(
                restaurant=account.restaurant,
                source_entity_id=source_entity_id,
                source_entity_type=source_entity_type,
                amount=amount,
                transaction_type='payment',
                category='order' if source_entity_type == 'order' else 'booking',
                status='completed',
                transaction_date=timezone.now(),
                notes=f"Payment from account balance for {source_entity_type}"
            )
            
            # Deduct from account balance
            account.balance -= amount
            account.save()
            
            # Update source entity status
            if source_entity_type == 'order':
                try:
                    order = Order.objects.get(id=source_entity_id)
                    order.status = 'confirmed'
                    order.save()
                except Order.DoesNotExist:
                    pass
            elif source_entity_type == 'booking':
                try:
                    booking = Booking.objects.get(id=source_entity_id)
                    booking.deposit_status = 'paid'
                    booking.status = 'confirmed'
                    booking.save()
                except Booking.DoesNotExist:
                    pass
            
            return Response({
                'message': 'Payment successful',
                'transaction_id': str(txn.transaction_id),
                'new_balance': str(account.balance),
                'amount_paid': str(amount)
            })
    
    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        """Get current account balance"""
        account = self.get_object()
        return Response({
            'account_id': str(account.account_id),
            'balance': str(account.balance),
            'account_type': account.account_type,
            'is_refundable': account.is_refundable,
            'restaurant': account.restaurant.name
        })
    
    @action(detail=True, methods=['get'])
    def transaction_history(self, request, pk=None):
        """Get account transaction history"""
        account = self.get_object()
        transactions = Transaction.objects.filter(
            source_entity_id=account.account_id,
            source_entity_type='customer_account'
        ).order_by('-created_at')[:50]  # Last 50 transactions
        
        history = []
        for txn in transactions:
            history.append({
                'transaction_id': str(txn.transaction_id),
                'amount': str(txn.amount),
                'transaction_type': txn.transaction_type,
                'status': txn.status,
                'date': txn.transaction_date,
                'notes': txn.notes
            })
        
        return Response({
            'account_id': str(account.account_id),
            'current_balance': str(account.balance),
            'transactions': history
        })