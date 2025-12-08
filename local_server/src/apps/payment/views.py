import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination

from apps.core.models import ActivityLog, Restaurant
from apps.order_processing.models import OfflineOrder

from apps.core import serializers

from .models import Invoice, Payment, PaymentAllocation, CustomerWallet, AccountingEntry
from .services import invoice_service, payment_service, wallet_service
from .serializers import (
    # Invoice
    InvoiceCreateSerializer,
    InvoiceReadSerializer,
    InvoiceStatusSerializer,
    
    # Payment
    PaymentInitiateSerializer,
    PaymentReadSerializer,
    PaymentAllocationSerializer,
    CashPaymentCompletionSerializer,
    WalletRefundSerializer,
    
    # Wallet
    WalletAddFundsSerializer,
    
    # Webhook
    PaymentWebhookSerializer,
    
    
)

# Filters
from django_filters.rest_framework import DjangoFilterBackend
from .filters import InvoiceFilter

# Response
from .serializers_util import ErrorResponseSerializer,SuccessResponseSerializer

from rest_framework.serializers import ValidationError

logger = logging.getLogger('dineswift.payment')


# =============================================================================
# CUSTOM PERMISSIONS
# =============================================================================

class IsRestaurantStaff(permissions.BasePermission):
    """Permission for restaurant staff members"""
    
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and 
                   hasattr(request.user, 'restaurant_id'))


class CanProcessRefund(permissions.BasePermission):
    """Permission to process refunds"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.is_staff or request.user.has_perm('payment.process_refund')


# =============================================================================
# CUSTOM PAGINATION
# =============================================================================

class PaymentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# =============================================================================
# VIEWSETS
# =============================================================================

class InvoiceViewSet(viewsets.ModelViewSet):
    """ViewSet for Invoice CRUD operations"""
    permission_classes = [IsAuthenticated, IsRestaurantStaff]
    pagination_class = PaymentPagination
    
    filter_backends = [DjangoFilterBackend] 
    filterset_class = InvoiceFilter
    
    def get_queryset(self):
        return Invoice.objects.filter(
            restaurant_id=self.request.user.restaurant_id
        ).select_related('order', 'restaurant')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCreateSerializer
        return InvoiceReadSerializer
    
    def perform_create(self, serializer):
        with transaction.atomic():
            invoice = serializer.save(
                restaurant_id=self.request.user.restaurant_id,
                status='ISSUED',
                due_date=timezone.now() + timedelta(hours=24)
            )
            
            # Log the activity
            ActivityLog.objects.create(
                level='INFO',
                module='INVOICE',
                action='INVOICE_CREATED',
                user=self.request.user,
                restaurant_id=self.request.user.restaurant_id,
                details={
                    'invoice_id': str(invoice.id),
                    'order_id': str(invoice.order.id),
                    'total_amount': float(invoice.total_amount),
                    'created_by': str(self.request.user.id)
                }
            )
            
            logger.info(
                f"Invoice created: {invoice.id} for order {invoice.order.id}",
                extra={
                    'user_id': str(self.request.user.id),
                    'restaurant_id': str(self.request.user.restaurant_id),
                    'invoice_id': str(invoice.id),
                    'amount': float(invoice.total_amount)
                }
            )
    
    
    def allocations(self, request, pk=None):
        """Get allocations for a specific invoice"""
        invoice = self.get_object()
        allocations = invoice.allocations.select_related('payment').all()
        serializer = PaymentAllocationSerializer(allocations, many=True)
        return Response(serializer.data)

class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for Payment operations"""
    permission_classes = [IsAuthenticated, IsRestaurantStaff]
    pagination_class = PaymentPagination
    
    def get_queryset(self):
        return Payment.objects.filter(
            restaurant_id=self.request.user.restaurant_id
        ).select_related('restaurant').prefetch_related('allocations')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentInitiateSerializer
        return PaymentReadSerializer
    
    def create(self, request, *args, **kwargs):
        # Using the serializer for validation
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Prepare data for service
            payment_data = serializer.validated_data.copy()
            payment_data['user_id'] = str(request.user.id)
            payment_data['restaurant_id'] = str(request.user.restaurant_id)
            
            # Call service
            result = payment_service.initiate_payment(
                payment_data=payment_data,
                user_id=str(request.user.id)
            )
            
            # Handle Service Failure
            if not result.get('success', False):
                
                # Use 400 or 402/403 depending on payment failure type
                raise ValidationError(result.get('error', 'Payment initiation failed'))

            # Return a DRF Response directly with the service result
            return Response(result, status=status.HTTP_201_CREATED)
        
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a payment"""
        payment = self.get_object()
        
        if payment.status not in ['PENDING', 'AWAITING_COLLECTION']:
            return Response(
                {'error': 'Payment cannot be cancelled in current state'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.status = 'CANCELLED'
        payment.save()
        
        # Log cancellation
        ActivityLog.objects.create(
            level='INFO',
            module='PAYMENT',
            action='PAYMENT_CANCELLED',
            user=request.user,
            restaurant_id=payment.restaurant_id,
            details={
                'payment_id': str(payment.id),
                'previous_status': payment.status,
                'cancelled_by': str(request.user.id)
            }
        )
        
        return Response({'success': True, 'message': 'Payment cancelled'})


# =============================================================================
# FUNCTION-BASED VIEWS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def get_invoice_status(request, invoice_id):
    """Get comprehensive invoice status with allocations"""
        
    try:
        # Verify invoice belongs to user's restaurant
        
        invoice = get_object_or_404(
            Invoice.objects.select_related('order', 'restaurant'),
            id=invoice_id,
            restaurant_id=request.user.restaurant_id
        )
        
        status_info = invoice_service.get_invoice_status(
            invoice_id=invoice_id,
            user_id=str(request.user.id)
        )
        
        if 'error' in status_info:
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': status_info['error'],
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Log access
        ActivityLog.objects.create(
            level='DEBUG',
            module='INVOICE',
            action='INVOICE_STATUS_REQUESTED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'invoice_id': str(invoice_id),
                'user_id': str(request.user.id),
                'ip_address': request.META.get('REMOTE_ADDR')
            }
        )
        
        return Response(
            SuccessResponseSerializer({
                'success': True,
                'message': 'Invoice status retrieved',
                'data': status_info,
                'correlation_id': str(uuid.uuid4())
            }).data
        )
        
    except Invoice.DoesNotExist:
        # Explicitly handle the DoesNotExist to return 404
        return Response(
            ErrorResponseSerializer({
                'error': 'Invoice not found',
                'error_code': 'INVOICE_NOT_FOUND',
            }).data,
            status=status.HTTP_404_NOT_FOUND
        )
        
    except Exception as e:
        logger.error(
            f"Failed to get invoice status: {str(e)}",
            extra={
                'invoice_id': str(invoice_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        # Log error
        ActivityLog.objects.create(
            level='ERROR',
            module='INVOICE',
            action='INVOICE_STATUS_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'invoice_id': str(invoice_id),
                'error': str(e),
                'traceback': logger.format_exc()
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve invoice status',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def get_payment_status(request, payment_id):
    """
    Get the comprehensive status and details for a specific payment.
    
    Args:
        payment_id (str): The ID of the Payment object to retrieve.
    """
    
    try:
        # 1. Verify payment belongs to user's restaurant
        payment = get_object_or_404(
            Payment.objects.select_related('invoice', 'restaurant'),
            id=payment_id,
            restaurant_id=request.user.restaurant_id
        )
        
        # Using service layer to get comprehensive status
        # This service call might hit external gateways or perform complex logic.
        status_info = payment_service.get_payment_status(
            payment_id=payment_id,
            user_id=str(request.user.id)
        )
        
        #  Handle Service Error (e.g., payment not found in gateway)
        if 'error' in status_info:
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': status_info['error'],
                    'correlation_id': str(uuid.uuid4())
                }).data,
                # Use 400 Bad Request if the ID is valid but the service fails
                status=status.HTTP_400_BAD_REQUEST 
            )
        
        # 4. Log successful access
        ActivityLog.objects.create(
            level='DEBUG',
            module='PAYMENT',
            action='PAYMENT_STATUS_REQUESTED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'payment_id': str(payment_id),
                'user_id': str(request.user.id),
                'ip_address': request.META.get('REMOTE_ADDR')
            }
        )
        
        # 5. Return success response
        return Response(
            SuccessResponseSerializer({
                'success': True,
                'message': 'Payment status retrieved',
                'data': status_info,
                'correlation_id': str(uuid.uuid4())
            }).data
        )
        
    except Payment.DoesNotExist:
        # Explicitly handle the DoesNotExist if get_object_or_404 fails
        return Response(
            ErrorResponseSerializer({
                'error': 'Payment not found or access denied',
                'error_code': 'PAYMENT_NOT_FOUND',
            }).data,
            status=status.HTTP_404_NOT_FOUND
        )
        
    except Exception as e:
        # 6. Log unhandled internal error
        logger.error(
            f"Failed to get payment status: {str(e)}",
            extra={
                'payment_id': str(payment_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='PAYMENT',
            action='PAYMENT_STATUS_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'payment_id': str(payment_id),
                'error': str(e),
                'traceback': logger.format_exc()
            }
        )
        
        # 7. Return 500 response for unhandled errors
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve payment status due to an internal error',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def get_order_invoice(request, order_id):
    """Get invoice for a specific order"""
    # Verify order belongs to restaurant
    order = get_object_or_404(
        OfflineOrder,
        id=order_id,
        restaurant_id=request.user.restaurant_id
    )

    try:
        
        # Get or create invoice
        try:
            invoice = order.invoice
        except Invoice.DoesNotExist:
            # Create invoice if doesn't exist
            invoice = invoice_service.create_invoice(
                order_id=str(order.id),
                restaurant_id=str(request.user.restaurant_id),
                amount=order.total_amount,
                tax_amount=order.tax_amount or Decimal('0'),
                service_fee=Decimal('0'),
                discount_amount=Decimal('0'),
                user_id=str(request.user.id)
            )
            
            if not invoice['success']:
                return Response(
                    ErrorResponseSerializer({
                        'success': False,
                        'error': invoice.get('error', 'Failed to create invoice'),
                        'correlation_id': str(uuid.uuid4())
                    }).data,
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            invoice = Invoice.objects.get(id=invoice['invoice_id'])
        
        serializer = InvoiceReadSerializer(invoice)
        
        return Response(
            SuccessResponseSerializer({
                'success': True,
                'message': 'Order invoice retrieved',
                'data': serializer.data,
                'correlation_id': str(uuid.uuid4())
            }).data
        )
        
    except OfflineOrder.DoesNotExist:
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Order not found',
                'error_code': 'ORDER_NOT_FOUND',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(
            f"Failed to get order invoice: {str(e)}",
            extra={
                'order_id': str(order_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='INVOICE',
            action='ORDER_INVOICE_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'order_id': str(order_id),
                'error': str(e)
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve order invoice',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def allocate_payment(request, payment_id):
    """Manually allocate payment to invoice"""
    try:
        serializer = PaymentAllocationSerializer(data={
            **request.data,
            'payment_id': payment_id,
            'allocated_amount': request.data.get('allocated_amount'),
            'allocated_by': str(request.user.id)
        })
        
        if not serializer.is_valid():
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': serializer.errors,
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Verify payment exists and belongs to restaurant
            payment = get_object_or_404(
                Payment,
                id=payment_id,
                restaurant_id=request.user.restaurant_id
            )
            
            # Verify invoice exists and belongs to restaurant
            invoice = get_object_or_404(
                Invoice,
                id=serializer.validated_data['invoice_id'],
                restaurant_id=request.user.restaurant_id
            )
            
            # Create allocation
            allocation = PaymentAllocation.objects.create(
                invoice=invoice,
                payment=payment,
                allocated_amount=serializer.validated_data['allocated_amount'],
                allocated_by=request.user
            )
            
            # Update invoice status
            invoice.mark_paid(serializer.validated_data['allocated_amount'])
            
            # Create accounting entry
            AccountingEntry.objects.create(
                restaurant=payment.restaurant,
                payment=payment,
                invoice=invoice,
                debit_account='cash' if payment.gateway == 'CASH' else 'accounts_receivable',
                credit_account='revenue',
                amount=serializer.validated_data['allocated_amount'],
                currency=payment.currency,
                reference_type='INVOICE_ALLOCATION',
                reference_id=allocation.id,
                description=f"Payment allocation from {payment.gateway}",
                created_by=request.user.id
            )
            
            # Log allocation
            ActivityLog.objects.create(
                level='INFO',
                module='PAYMENT',
                action='PAYMENT_ALLOCATED',
                user=request.user,
                restaurant_id=request.user.restaurant_id,
                details={
                    'allocation_id': str(allocation.id),
                    'payment_id': str(payment.id),
                    'invoice_id': str(invoice.id),
                    'amount': float(serializer.validated_data['allocated_amount']),
                    'allocated_by': str(request.user.id)
                }
            )
            
            logger.info(
                f"Payment {payment.id} allocated to invoice {invoice.id}",
                extra={
                    'payment_id': str(payment.id),
                    'invoice_id': str(invoice.id),
                    'amount': float(serializer.validated_data['allocated_amount']),
                    'user_id': str(request.user.id)
                }
            )
            
            return Response(
                SuccessResponseSerializer({
                    'success': True,
                    'message': 'Payment allocated successfully',
                    'data': PaymentAllocationSerializer(allocation).data,
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_201_CREATED
            )
            
    except Exception as e:
        logger.error(
            f"Payment allocation failed: {str(e)}",
            extra={
                'payment_id': str(payment_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='PAYMENT',
            action='PAYMENT_ALLOCATION_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'payment_id': str(payment_id),
                'error': str(e),
                'request_data': request.data
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': f'Payment allocation failed: {str(e)}',
                'error_code': 'ALLOCATION_FAILED',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def complete_cash_payment(request, payment_id):
    """Complete cash payment collection"""
    try:
        serializer = CashPaymentCompletionSerializer(data={
            'payment_id': payment_id,
            'staff_user_id': str(request.user.id)
        })
        
        if not serializer.is_valid():
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': serializer.errors,
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = payment_service.complete_cash_payment(
            payment_id=payment_id,
            staff_user_id=str(request.user.id)
        )
        
        if result['success']:
            return Response(
                SuccessResponseSerializer({
                    'success': True,
                    'message': 'Cash payment completed successfully',
                    'data': result,
                    'correlation_id': str(uuid.uuid4())
                }).data
            )
        else:
            ActivityLog.objects.create(
                level='WARNING',
                module='PAYMENT',
                action='CASH_PAYMENT_COMPLETION_FAILED',
                user=request.user,
                restaurant_id=request.user.restaurant_id,
                details={
                    'payment_id': str(payment_id),
                    'error': result.get('error'),
                    'staff_user_id': str(request.user.id)
                }
            )
            
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': result.get('error', 'Cash payment completion failed'),
                    'error_code': 'CASH_PAYMENT_FAILED',
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(
            f"Cash payment completion failed: {str(e)}",
            extra={
                'payment_id': str(payment_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='PAYMENT',
            action='CASH_PAYMENT_COMPLETION_ERROR',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'payment_id': str(payment_id),
                'error': str(e),
                'traceback': logger.format_exc()
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Cash payment completion failed',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanProcessRefund])
def request_refund(request, payment_id):
    """Request refund for a payment"""
    try:
        serializer = WalletRefundSerializer(data={
            **request.data,
            'user_id': str(request.user.id),
            'restaurant_id': str(request.user.restaurant_id)
        })
        
        if not serializer.is_valid():
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': serializer.errors,
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = wallet_service.process_refund(
            user_id=str(request.user.id),
            restaurant_id=str(request.user.restaurant_id),
            refund_id=str(uuid.uuid4()),
            amount=serializer.validated_data['amount'],
            original_payment_ref=payment_id,
            wallet_type=serializer.validated_data.get('wallet_type', 'PREPAID'),
            correlation_id=serializer.validated_data.get('correlation_id')
        )
        
        if result:
            # Update payment status
            payment = get_object_or_404(Payment, id=payment_id)
            payment.status = 'REFUNDED'
            payment.save()
            
            # Create refund record
            ActivityLog.objects.create(
                level='INFO',
                module='PAYMENT',
                action='REFUND_PROCESSED',
                user=request.user,
                restaurant_id=request.user.restaurant_id,
                details={
                    'payment_id': str(payment_id),
                    'refund_amount': float(serializer.validated_data['amount']),
                    'refunded_to_wallet': True,
                    'processed_by': str(request.user.id)
                }
            )
            
            return Response(
                SuccessResponseSerializer({
                    'success': True,
                    'message': 'Refund processed successfully',
                    'data': {
                        'payment_id': str(payment_id),
                        'refund_amount': float(serializer.validated_data['amount']),
                        'status': 'REFUNDED'
                    },
                    'correlation_id': str(uuid.uuid4())
                }).data
            )
        else:
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': 'Refund processing failed',
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(
            f"Refund request failed: {str(e)}",
            extra={
                'payment_id': str(payment_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='PAYMENT',
            action='REFUND_REQUEST_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'payment_id': str(payment_id),
                'error': str(e),
                'request_data': request.data
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Refund request failed',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def get_invoice_payments(request, invoice_id):
    """
    Get all payments and allocation details for a specific Invoice.
    The primary ID used for lookup is the Invoice ID.
    """
    try:
        # Verify invoice belongs to the restaurant
        invoice = get_object_or_404(
            Invoice,
            id=invoice_id,
            restaurant_id=request.user.restaurant_id
        )

        # Get payments allocated to this invoice
        # Query Payment objects that have an allocation linked to this invoice
        payments = Payment.objects.filter(
            allocations__invoice=invoice
        ).distinct()
        
        # Serialize the payment data
        serializer = PaymentReadSerializer(payments, many=True)
        
        # Return success response
        return Response(
            SuccessResponseSerializer({
                'success': True,
                'message': 'Invoice payments retrieved successfully',
                'data': {
                    'invoice_id': str(invoice_id),
                    'order_id': str(invoice.order.id) if invoice.order else None, # Include order ID if present
                    'total_amount': float(invoice.total_amount),
                    'amount_paid': float(invoice.amount_paid),
                    'amount_due': float(invoice.amount_due),
                    'payments': serializer.data
                },
                'correlation_id': str(uuid.uuid4())
            }).data
        )

    except Invoice.DoesNotExist:
        # Handled by get_object_or_404, returns HTTP 404
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Invoice not found',
                'error_code': 'INVOICE_NOT_FOUND',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        # Handle unexpected exceptions
        logger.error(
            f"Failed to get invoice payments: {str(e)}",
            extra={
                'invoice_id': str(invoice_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        # Log activity for server error
        ActivityLog.objects.create(
            level='ERROR',
            module='PAYMENT',
            action='INVOICE_PAYMENTS_FAILED', # Renamed action
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'invoice_id': str(invoice_id),
                'error': str(e)
            }
        )
        
        # 7. Return HTTP 500
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve invoice payments due to server error',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsRestaurantStaff])
def get_order_payments(request, order_id):
    """Get all payments for an order"""
    try:
        # Verify order belongs to restaurant
        order = get_object_or_404(
            OfflineOrder,
            id=order_id,
            restaurant_id=request.user.restaurant_id
        )
        
        # Get payments through invoice
        try:
            invoice = order.invoice
            payments = Payment.objects.filter(
                allocations__invoice=invoice
            ).distinct()
            
            serializer = PaymentReadSerializer(payments, many=True)
            
            return Response(
                SuccessResponseSerializer({
                    'success': True,
                    'message': 'Order payments retrieved',
                    'data': {
                        'order_id': str(order_id),
                        'total_amount': float(invoice.total_amount),
                        'amount_paid': float(invoice.amount_paid),
                        'amount_due': float(invoice.amount_due),
                        'payments': serializer.data
                    },
                    'correlation_id': str(uuid.uuid4())
                }).data
            )
            
        except Invoice.DoesNotExist:
            return Response(
                SuccessResponseSerializer({
                    'success': True,
                    'message': 'No invoice found for order',
                    'data': {
                        'order_id': str(order_id),
                        'payments': []
                    },
                    'correlation_id': str(uuid.uuid4())
                }).data
            )
        
    except OfflineOrder.DoesNotExist:
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Order not found',
                'error_code': 'ORDER_NOT_FOUND',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(
            f"Failed to get order payments: {str(e)}",
            extra={
                'order_id': str(order_id),
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='PAYMENT',
            action='ORDER_PAYMENTS_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'order_id': str(order_id),
                'error': str(e)
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve order payments',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
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
        wallet_type = request.GET.get('wallet_type', 'PREPAID')
        
        balance_info = wallet_service.get_wallet_balance(
            user_id=str(request.user.id),
            restaurant_id=str(request.user.restaurant_id),
            wallet_type=wallet_type
        )
        
        ActivityLog.objects.create(
            level='DEBUG',
            module='WALLET',
            action='WALLET_BALANCE_REQUESTED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'wallet_type': wallet_type,
                'ip_address': request.META.get('REMOTE_ADDR')
            }
        )
        
        return Response(
            SuccessResponseSerializer({
                'success': True,
                'message': 'Wallet balance retrieved',
                'data': balance_info,
                'correlation_id': str(uuid.uuid4())
            }).data
        )
        
    except Exception as e:
        logger.error(
            f"Failed to get wallet balance: {str(e)}",
            extra={
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='WALLET',
            action='WALLET_BALANCE_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'error': str(e)
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve wallet balance',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_transactions(request):
    """Get wallet transaction history"""
    try:
        wallet_type = request.GET.get('wallet_type', 'PREPAID')
        limit = int(request.GET.get('limit', 50))
        
        # Get wallet
        wallet = get_object_or_404(
            CustomerWallet,
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            wallet_type=wallet_type
        )
        
        # Get transactions
        transactions = wallet.transactions.all()[:limit]
        
        from .serializers import WalletTransactionReadSerializer
        serializer = WalletTransactionReadSerializer(transactions, many=True)
        
        ActivityLog.objects.create(
            level='DEBUG',
            module='WALLET',
            action='WALLET_TRANSACTIONS_REQUESTED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'wallet_type': wallet_type,
                'transaction_count': len(transactions),
                'ip_address': request.META.get('REMOTE_ADDR')
            }
        )
        
        return Response(
            SuccessResponseSerializer({
                'success': True,
                'message': 'Wallet transactions retrieved',
                'data': serializer.data,
                'correlation_id': str(uuid.uuid4())
            }).data
        )
        
    except CustomerWallet.DoesNotExist:
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Wallet not found',
                'error_code': 'WALLET_NOT_FOUND',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(
            f"Failed to get wallet transactions: {str(e)}",
            extra={
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='WALLET',
            action='WALLET_TRANSACTIONS_FAILED',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'error': str(e)
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to retrieve wallet transactions',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_wallet_funds(request):
    """Add funds to customer wallet"""
    try:
        serializer = WalletAddFundsSerializer(data={
            **request.data,
            'user_id': str(request.user.id),
            'restaurant_id': str(request.user.restaurant_id)
        })
        
        if not serializer.is_valid():
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': serializer.errors,
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = wallet_service.add_funds(
            user_id=str(request.user.id),
            restaurant_id=str(request.user.restaurant_id),
            amount=serializer.validated_data['amount'],
            reference_type=serializer.validated_data['reference_type'],
            reference_id=serializer.validated_data['reference_id'],
            description=serializer.validated_data['description'],
            correlation_id=serializer.validated_data.get('correlation_id')
        )
        
        if result['success']:
            return Response(
                SuccessResponseSerializer({
                    'success': True,
                    'message': 'Funds added to wallet successfully',
                    'data': result,
                    'correlation_id': result.get('correlation_id', str(uuid.uuid4()))
                }).data
            )
        else:
            ActivityLog.objects.create(
                level='WARNING',
                module='WALLET',
                action='ADD_FUNDS_FAILED',
                user=request.user,
                restaurant_id=request.user.restaurant_id,
                details={
                    'amount': float(serializer.validated_data['amount']),
                    'error': result.get('error'),
                    'reference_id': serializer.validated_data['reference_id']
                }
            )
            
            return Response(
                ErrorResponseSerializer({
                    'success': False,
                    'error': result.get('error', 'Failed to add funds'),
                    'error_code': 'ADD_FUNDS_FAILED',
                    'correlation_id': str(uuid.uuid4())
                }).data,
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(
            f"Failed to add wallet funds: {str(e)}",
            extra={
                'user_id': str(request.user.id),
                'error': str(e)
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='ERROR',
            module='WALLET',
            action='ADD_FUNDS_ERROR',
            user=request.user,
            restaurant_id=request.user.restaurant_id,
            details={
                'error': str(e),
                'request_data': request.data
            }
        )
        
        return Response(
            ErrorResponseSerializer({
                'success': False,
                'error': 'Failed to add funds to wallet',
                'error_code': 'INTERNAL_SERVER_ERROR',
                'correlation_id': str(uuid.uuid4())
            }).data,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =============================================================================
# WEBHOOK VIEWS (No authentication required)
# =============================================================================

@api_view(['POST'])
@permission_classes([])
def momo_webhook(request):
    """Handle Momo payment webhook"""
    correlation_id = request.META.get('HTTP_X_CORRELATION_ID', str(uuid.uuid4()))
    
    try:
        # Log incoming webhook
        ActivityLog.objects.create(
            level='INFO',
            module='PAYMENT',
            action='MOMO_WEBHOOK_RECEIVED',
            ip_address=request.META.get('REMOTE_ADDR'),
            correlation_id=correlation_id,
            details={
                'headers': dict(request.headers),
                'data': request.data,
                'source_ip': request.META.get('REMOTE_ADDR')
            }
        )
        
        serializer = PaymentWebhookSerializer(data=request.data)
        if not serializer.is_valid():
            ActivityLog.objects.create(
                level='WARNING',
                module='PAYMENT',
                action='MOMO_WEBHOOK_VALIDATION_FAILED',
                correlation_id=correlation_id,
                details={
                    'errors': serializer.errors,
                    'data': request.data
                }
            )
            
            return Response(
                {'error': 'Invalid webhook data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = payment_service.handle_webhook(
            webhook_data=serializer.validated_data,
            gateway='MOMO'
        )
        
        if result['success']:
            ActivityLog.objects.create(
                level='INFO',
                module='PAYMENT',
                action='MOMO_WEBHOOK_PROCESSED',
                correlation_id=correlation_id,
                details={
                    'external_id': serializer.validated_data.get('external_id'),
                    'status': serializer.validated_data.get('status'),
                    'result': result
                }
            )
            
            return Response({'status': 'success'})
        else:
            ActivityLog.objects.create(
                level='ERROR',
                module='PAYMENT',
                action='MOMO_WEBHOOK_PROCESSING_FAILED',
                correlation_id=correlation_id,
                details={
                    'error': result.get('error'),
                    'data': request.data
                }
            )
            
            return Response(
                {'error': result.get('error')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(
            f"Momo webhook processing failed: {str(e)}",
            extra={
                'correlation_id': correlation_id,
                'error': str(e),
                'data': request.data
            },
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='CRITICAL',
            module='PAYMENT',
            action='MOMO_WEBHOOK_CRITICAL_ERROR',
            correlation_id=correlation_id,
            details={
                'error': str(e),
                'traceback': logger.format_exc(),
                'data': request.data
            }
        )
        
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def card_webhook(request):
    """Handle card payment webhook"""
    correlation_id = request.META.get('HTTP_X_CORRELATION_ID', str(uuid.uuid4()))
    
    try:
        ActivityLog.objects.create(
            level='INFO',
            module='PAYMENT',
            action='CARD_WEBHOOK_RECEIVED',
            ip_address=request.META.get('REMOTE_ADDR'),
            correlation_id=correlation_id,
            details={
                'headers': dict(request.headers),
                'data': request.data
            }
        )
        
        serializer = PaymentWebhookSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'error': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = payment_service.handle_webhook(
            webhook_data=serializer.validated_data,
            gateway='CARD'
        )
        
        return Response({'status': 'success' if result['success'] else 'failed'})
            
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
    correlation_id = request.META.get('HTTP_X_CORRELATION_ID', str(uuid.uuid4()))
    
    try:
        ActivityLog.objects.create(
            level='INFO',
            module='PAYMENT',
            action='GENERIC_WEBHOOK_RECEIVED',
            ip_address=request.META.get('REMOTE_ADDR'),
            correlation_id=correlation_id,
            details={
                'headers': dict(request.headers),
                'data': request.data
            }
        )
        
        serializer = PaymentWebhookSerializer(data=request.data)
        if not serializer.is_valid():
            ActivityLog.objects.create(
                level='WARNING',
                module='PAYMENT',
                action='WEBHOOK_VALIDATION_FAILED',
                correlation_id=correlation_id,
                details={'errors': serializer.errors}
            )
            return Response(
                {'error': 'Invalid webhook data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract gateway from headers or request data
        gateway = request.META.get('HTTP_X_GATEWAY') or request.data.get('gateway')
        
        if not gateway:
            ActivityLog.objects.create(
                level='WARNING',
                module='PAYMENT',
                action='WEBHOOK_GATEWAY_MISSING',
                correlation_id=correlation_id,
                details={'data': request.data}
            )
            return Response(
                {'error': 'Payment gateway not specified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = payment_service.handle_webhook(
            webhook_data=serializer.validated_data,
            gateway=gateway.upper()
        )
        
        if result['success']:
            ActivityLog.objects.create(
                level='INFO',
                module='PAYMENT',
                action='WEBHOOK_PROCESSED_SUCCESS',
                correlation_id=correlation_id,
                details={
                    'gateway': gateway,
                    'external_id': serializer.validated_data.get('external_id')
                }
            )
            return Response({'status': 'success'})
        else:
            ActivityLog.objects.create(
                level='ERROR',
                module='PAYMENT',
                action='WEBHOOK_PROCESSING_FAILED',
                correlation_id=correlation_id,
                details={
                    'gateway': gateway,
                    'error': result.get('error')
                }
            )
            return Response(
                {'error': result.get('error')},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(
            f"Generic webhook processing failed: {str(e)}",
            extra={'correlation_id': correlation_id},
            exc_info=True
        )
        
        ActivityLog.objects.create(
            level='CRITICAL',
            module='PAYMENT',
            action='WEBHOOK_CRITICAL_ERROR',
            correlation_id=correlation_id,
            details={'error': str(e), 'traceback': logger.format_exc()}
        )
        
        return Response(
            {'error': 'Webhook processing failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )