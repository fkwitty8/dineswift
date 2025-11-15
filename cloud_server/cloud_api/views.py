from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Order, OrderItem, SalesOrder, BillingRecord, CustomerAccount
from .serializers import OrderSerializer
from .account_utils import check_sufficient_balance

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def get_queryset(self):
        queryset = Order.objects.select_related('salesorder', 'billingrecord').prefetch_related('orderitem_set')
        restaurant_id = self.request.query_params.get('restaurant_id')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        return queryset
    
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if new_status in dict(Order.STATUS_CHOICES):
            order.status = new_status
            order.save()
            return Response({'status': 'updated'})
        return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def add_billing(self, request, pk=None):
        order = self.get_object()
        billing_data = request.data
        billing_data['order'] = order.id
        
        billing_record, created = BillingRecord.objects.get_or_create(
            order=order,
            defaults={
                'subtotal_amount': billing_data.get('subtotal_amount', 0),
                'tax_amount': billing_data.get('tax_amount', 0),
                'service_charge': billing_data.get('service_charge', 0),
                'discount_amount': billing_data.get('discount_amount', 0),
                'total_amount': billing_data.get('total_amount', 0),
                'billing_status': billing_data.get('billing_status', 'pending')
            }
        )
        
        return Response({'billing_id': str(billing_record.billing_id), 'created': created})
    
    @action(detail=True, methods=['post'])
    def pay_with_account(self, request, pk=None):
        order = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            account = CustomerAccount.objects.get(
                user_id=user_id,
                restaurant=order.restaurant,
                account_type='wallet'
            )
            
            if not check_sufficient_balance(account, order.total_amount):
                return Response({
                    'error': 'Insufficient balance',
                    'required': str(order.total_amount),
                    'available': str(account.balance)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Process payment via account endpoint
            from django.urls import reverse
            from django.test import RequestFactory
            factory = RequestFactory()
            
            # This would typically be handled by calling the account payment endpoint
            return Response({
                'message': 'Use account payment endpoint',
                'account_id': str(account.account_id),
                'endpoint': f'/api/accounts/{account.account_id}/pay_from_account/'
            })
            
        except CustomerAccount.DoesNotExist:
            return Response({
                'error': 'Customer account not found',
                'suggestion': 'Create account and deposit funds first'
            }, status=status.HTTP_404_NOT_FOUND)