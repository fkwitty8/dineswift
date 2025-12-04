import logging
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from decimal import Decimal
from apps.core.models import ActivityLog,Restaurant
from apps.core.services.supabase_client import supabase_client
from .models import Invoice, Payment, PaymentAllocation, CustomerWallet, AccountingEntry
import uuid
from .exceptions import InsufficientFundsError, InvalidPendingCaptureError,WalletError


from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger('dineswift')

class InvoiceService:
    """Service for invoice operations with comprehensive logging"""
    
    def create_invoice(self, order_id: str, restaurant_id: str, amount: Decimal, 
                      tax_amount: Decimal = 0, service_fee: Decimal = 0, 
                      discount_amount: Decimal = 0, user_id: str = None) -> dict:
        """Create invoice for an order"""
        try:
            from apps.order_processing.models import OfflineOrder
            
            order = OfflineOrder.objects.get(id=order_id, restaurant_id=restaurant_id)
            
            invoice = Invoice.objects.create(
                order=order,
                restaurant_id=restaurant_id,
                subtotal_amount=amount,
                tax_amount=tax_amount,
                service_fee=service_fee,
                discount_amount=discount_amount,
                total_amount=amount + tax_amount + service_fee - discount_amount,
                due_date=timezone.now() + timedelta(hours=24),
                status='ISSUED'
            )
            
            # Activity Log
            ActivityLog.objects.create(
                level='INFO',
                module='INVOICE',
                action='INVOICE_CREATED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                details={
                    'invoice_id': str(invoice.id),
                    'order_id': order_id,
                    'total_amount': float(invoice.total_amount),
                    'subtotal_amount': float(invoice.subtotal_amount),
                    'tax_amount': float(invoice.tax_amount),
                    'service_fee': float(invoice.service_fee),
                    'discount_amount': float(invoice.discount_amount)
                }
            )
            
            # Logger
            logger.info(
                f'Invoice created for order {order_id}',
                extra={
                    'invoice_id': str(invoice.id),
                    'order_id': order_id,
                    'restaurant_id': restaurant_id,
                    'total_amount': float(invoice.total_amount)
                }
            )
            
            return {
                'success': True,
                'invoice_id': str(invoice.id),
                'order_id': order_id,
                'total_amount': float(invoice.total_amount),
                'amount_due': float(invoice.amount_due)
            }
            
        except OfflineOrder.DoesNotExist:
            error_message = 'Order not found for the given ID and restaurant.'
            ActivityLog.objects.create(
                level='WARNING',
                module='INVOICE',
                action='INVOICE_CREATION_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                details={
                    'order_id': order_id,
                    'error': error_message,
                    'amount': float(amount)
                }
            )
            
            return {'success': False, 'error': error_message}
            
        except Exception as e:
            # Error logging
            ActivityLog.objects.create(
                level='ERROR',
                module='INVOICE',
                action='INVOICE_CREATION_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                details={
                    'order_id': order_id,
                    'error': str(e),
                    'amount': float(amount)
                }
            )
            
            logger.error(
                f'Invoice creation failed for order {order_id}: {str(e)}',
                extra={'order_id': order_id, 'error': str(e)},
                exc_info=True
            )
            
            return {'success': False, 'error': str(e)}
    
    def get_invoice_status(self, invoice_id: str, user_id: str = None) -> dict:
        """Get comprehensive invoice status with allocations"""
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            allocations = invoice.allocations.select_related('payment').all()
            
            # Log invoice access
            ActivityLog.objects.create(
                level='DEBUG',
                module='INVOICE',
                action='INVOICE_ACCESSED',
                user_id=user_id,
                restaurant_id=invoice.restaurant_id,
                details={
                    'invoice_id': str(invoice.id),
                    'order_id': str(invoice.order.id),
                    'status': invoice.status
                }
            )
            
            allocation_data = []
            for allocation in allocations:
                allocation_data.append({
                    'allocation_id': str(allocation.id),
                    'payment_id': str(allocation.payment.id),
                    'allocated_amount': float(allocation.allocated_amount),
                    'allocation_date': allocation.allocation_date.isoformat(),
                    'payment_status': allocation.payment.status,
                    'payment_gateway': allocation.payment.gateway
                })
            
            return {
                'invoice_id': str(invoice.id),
                'order_id': str(invoice.order.id),
                'status': invoice.status,
                'total_amount': float(invoice.total_amount),
                'amount_paid': float(invoice.amount_paid),
                'amount_due': float(invoice.amount_due),
                'is_fully_paid': invoice.is_fully_paid,
                'is_overdue': invoice.is_overdue,
                'due_date': invoice.due_date.isoformat(),
                'paid_at': invoice.paid_at.isoformat() if invoice.paid_at else None,
                'allocations': allocation_data,
                'created_at': invoice.created_at.isoformat(),
                'updated_at': invoice.updated_at.isoformat()
            }
            
        except Invoice.DoesNotExist:
            ActivityLog.objects.create(
                level='WARNING',
                module='INVOICE',
                action='INVOICE_NOT_FOUND',
                user_id=user_id,
                details={'invoice_id': invoice_id}
            )
            return {'error': 'Invoice not found'}
        except Exception as e:
            logger.error(
                f'Failed to get invoice status: {str(e)}',
                extra={'invoice_id': invoice_id, 'error': str(e)},
                exc_info=True
            )
            return {'error': 'Failed to retrieve invoice status'}


class PaymentService:
    """
    Comprehensive Payment Service with proper Invoice-AccountingEntry linking
    """
    def initiate_payment(self, payment_data: dict, user_id: str = None) -> dict:
        """Initiate payment process with proper invoice linking"""
        try:
            with transaction.atomic():
                invoice_id = payment_data['invoice_id']
                invoice = Invoice.objects.get(
                    id=invoice_id,
                    status__in=['DRAFT', 'ISSUED', 'PARTIALLY_PAID']
                )
                
                
                # Create payment record
                payment = Payment.objects.create(
                    restaurant=invoice.restaurant,
                    amount=Decimal(payment_data.get('amount', invoice.total_amount)),  # Using actual total amount from the api. to catter for partial payments
                    currency='UGX',  # Default currency
                    gateway=payment_data['payment_method'].upper(),
                    customer_phone=payment_data.get('customer_phone'),
                    customer_email=payment_data.get('customer_email'),
                    customer_user_id=user_id
                )
                
                gateway_handlers = {
                    'CASH': self._initiate_cash_payment,
                    'MOMO': self._initiate_momo_payment,
                    'VISA': self._initiate_card_payment,
                    'MASTERCARD': self._initiate_card_payment,
                    'WALLET': self._process_wallet_payment,
                    'CRYPTO': self._initiate_crypto_payment,
                }
                
                handler = gateway_handlers.get(payment.gateway)
                if handler:
                    result = handler(payment, invoice, user_id)
                else:
                    raise ValueError(f"Unsupported payment gateway: {payment.gateway}")
                
                # Log payment creation
                ActivityLog.objects.create(
                    level='INFO',
                    module='PAYMENT',
                    action='PAYMENT_CREATED',
                    user_id=user_id,
                    restaurant_id=payment.restaurant_id,
                    details={
                        'payment_id': str(payment.id),
                        'invoice_id': str(invoice.id),
                        'gateway': payment.gateway,
                        'status': payment.status,
                        'amount': float(payment.amount)
                    }
                )
                
                return {
                    'success': True,
                    'payment_id': str(payment.id),
                    'invoice_id': str(invoice.id),
                    'status': payment.status,
                    'gateway': payment.gateway,
                    **result  # Include gateway-specific data
                }
                
        except Exception as e:
            logger.error(f"Payment initiation failed: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _initiate_cash_payment(self, payment: Payment, invoice: Invoice, user_id: str) -> dict:
        """Cash payment - set to AWAITING_COLLECTION and notify staff"""
        payment.status = 'AWAITING_COLLECTION'
        payment.save(update_fields=['status'])
        
        # Trigger real-time notification to staff
        self._notify_staff_cash_payment(payment, invoice)
        
        return {
            'message': 'Payment awaiting collection by staff',
            'requires_staff_action': True
        }
    
    def _notify_staff_cash_payment(self, payment: Payment, invoice: Invoice):
        """Notify staff about cash payment awaiting collection"""
        try:
            # Real-time notification via WebSocket or push notification
            notification_data = {
                'type': 'CASH_PAYMENT_AWAITING_COLLECTION',
                'payment_id': str(payment.id),
                'invoice_id': str(invoice.id),
                'order_id': str(invoice.order.id),
                'amount': float(payment.amount),
                'customer_phone': payment.customer_phone,
                'timestamp': timezone.now().isoformat()
            }
            
            # Send via your preferred real-time service, Django Channels,
            
            self._send_real_time_notification(
                room=f"restaurant_{payment.restaurant_id}_staff",
                event='payment_awaiting_collection',
                data=notification_data
            )
            
            logger.info(f"Cash payment notification sent for payment {payment.id}")
            
        except Exception as e:
            logger.error(f"Failed to send staff notification: {str(e)}")

    # Update the _notify_staff_cash_payment method to use the new notification system

    def _notify_staff_cash_payment(self, payment: Payment, invoice: Invoice):
        """Enhanced staff notification for cash payments using real-time notifications"""
        try:
            notification_data = {
                'payment_id': str(payment.id),
                'invoice_id': str(invoice.id),
                'order_id': str(invoice.order.id),
                'amount': float(payment.amount),
                'currency': payment.currency,
                'customer_phone': payment.customer_phone,
                'customer_email': payment.customer_email,
                'order_type': getattr(invoice.order, 'order_type', 'Dine-in'),
                'table_number': getattr(invoice.order, 'table_number', 'N/A'),
                'customer_name': getattr(invoice.order, 'customer_name', 'N/A'),
                'items_count': getattr(invoice.order, 'items_count', 0),
                'urgency': 'high',
                'action_required': True,
                'action_type': 'collect_cash_payment'
            }

            # Send real-time notification
            self._send_real_time_notification(
                room=str(payment.restaurant_id),
                event='payment_awaiting_collection',
                data=notification_data
            )

            # Also log for audit trail
            ActivityLog.objects.create(
                level='INFO',
                module='NOTIFICATION',
                action='STAFF_NOTIFIED_CASH_PAYMENT',
                restaurant_id=payment.restaurant_id,
                details={
                    'payment_id': str(payment.id),
                    'notification_data': notification_data,
                    'delivery_method': 'websocket',
                    'room': f"restaurant_{payment.restaurant_id}_staff"
                }
            )

            logger.info(f"Real-time notification sent for cash payment {payment.id}")

        except Exception as e:
            logger.error(f"Staff notification failed: {str(e)}")
            # Don't break the payment flow if notification fails

    def complete_cash_payment(self, payment_id: str, staff_user_id: str) -> dict:
        """Staff confirms cash collection - completes the payment"""
        try:
            with transaction.atomic():
                # Lock payment for update to prevent race conditions
                payment = Payment.objects.select_for_update().get(
                    id=payment_id, 
                    status='AWAITING_COLLECTION'
                )
                
                # Get the associated invoice
                allocations = payment.allocations.select_related('invoice').all()
                if not allocations:
                    return {'success': False, 'error': 'No invoice allocation found'}
                
                invoice = allocations[0].invoice
                
                #  Final cash validation (physical validation by staff)
                self._validate_cash_payment_physical(payment)
                
                # Mark payment as completed
                payment.mark_completed()
                
                # Update invoice status 
                if invoice.amount_due <= 0:
                    invoice.status = 'PAID'
                    invoice.paid_at = timezone.now()
                    invoice.save()
                
                # Log staff completion
                ActivityLog.objects.create(
                    level='INFO',
                    module='PAYMENT',
                    action='CASH_PAYMENT_COLLECTED',
                    user_id=staff_user_id,
                    restaurant_id=payment.restaurant_id,
                    details={
                        'payment_id': str(payment.id),
                        'invoice_id': str(invoice.id),
                        'collected_by': staff_user_id,
                        'amount': float(payment.amount)
                    }
                )
                
                return {
                    'success': True,
                    'payment_id': str(payment.id),
                    'status': payment.status,
                    'completed_at': payment.completed_at.isoformat()
                }
                
        except Payment.DoesNotExist:
            return {'success': False, 'error': 'Payment not found or not awaiting collection'}
        except Exception as e:
            logger.error(f"Cash payment completion failed: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _validate_cash_payment_physical(self, payment: Payment):
        """Physical cash validation by staff"""
        #we shall have to check whether the cash is valid or not
        # This is where actual cash validation happens
        # Check for counterfeit, count accuracy, etc.
        # Could integrate with cash drawer systems
        logger.info(f"Physical cash validation completed for payment {payment.id}")
        
        # For now, we'll assume validation passes
        # In production, you might want more sophisticated validation
        return True
    
    
    def _send_real_time_notification(self, room: str, event: str, data: dict):
        """
        Send real-time notification via Django Channels WebSocket.
        Handles both sync and async contexts with proper error handling.
        """
        try:
            # Get the channel layer
            channel_layer = get_channel_layer()
            
            # Prepare the notification payload
            notification_payload = {
                'type': 'staff.notification',  # This matches the consumer method name
                'event': event,
                'data': data,
                'timestamp': self._get_current_timestamp(),
                'server_id': getattr(settings, 'SERVER_ID', 'local'),
            }
            
            # Send to the specific restaurant room
            group_name = f"restaurant_{room}_staff"
            
            # Use async_to_sync to call async channel layer from sync context
            async_to_sync(channel_layer.group_send)(
                group_name,
                notification_payload
            )
            
            logger.info(
                f"Real-time notification sent to room {group_name} for event {event}",
                extra={
                    'room': room,
                    'event': event,
                    'group_name': group_name,
                    'data_keys': list(data.keys())
                }
            )
            
        except Exception as e:
            # Don't break the payment flow if notifications fail
            logger.error(
                f"Failed to send real-time notification: {str(e)}",
                extra={
                    'room': room,
                    'event': event,
                    'error': str(e)
                },
                exc_info=True
            )
            
            # Fallback: Log to activity log for manual follow-up
            self._create_notification_fallback_log(room, event, data, str(e))

    def _get_current_timestamp(self):
        """Get current timestamp in ISO format"""
        from django.utils import timezone
        return timezone.now().isoformat()

    def _create_notification_fallback_log(self, room: str, event: str, data: dict, error: str):
        """Create fallback activity log when real-time notification fails"""
        from apps.core.models import ActivityLog
        
        try:
            ActivityLog.objects.create(
                level='WARNING',
                module='NOTIFICATION',
                action='REALTIME_NOTIFICATION_FAILED',
                restaurant_id=room,
                details={
                    'event': event,
                    'data': data,
                    'error': error,
                    'fallback_used': True,
                    'timestamp': self._get_current_timestamp()
                }
            )
        except Exception as log_error:
            # If even logging fails, use basic logging
            logger.critical(
                f"Critical: Notification and fallback logging both failed: {str(log_error)}"
            )

    # Optional: Async version for use in async contexts
    async def _send_real_time_notification_async(self, room: str, event: str, data: dict):
        """
        Async version of real-time notification for use in async contexts.
        """
        try:
            channel_layer = get_channel_layer()
            
            notification_payload = {
                'type': 'staff.notification',
                'event': event,
                'data': data,
                'timestamp': self._get_current_timestamp(),
                'server_id': getattr(settings, 'SERVER_ID', 'local'),
            }
            
            group_name = f"restaurant_{room}_staff"
            
            await channel_layer.group_send(
                group_name,
                notification_payload
            )
            
            logger.info(
                f"Async real-time notification sent to {group_name} for {event}"
            )
            
        except Exception as e:
            logger.error(f"Async notification failed: {str(e)}")
            # For async context, we might want to handle differently
            raise
        
    
    def _create_payment_accounting_entry(self, payment: Payment, invoice: Invoice, amount: Decimal, user_id: str = None):
        """Create accounting entry for payment with invoice reference"""
        # Determine accounts based on payment gateway
        if payment.gateway in ['CASH', 'WALLET']:
            debit_account = 'cash'
        else:
            debit_account = 'accounts_receivable'
        
        AccountingEntry.objects.create(
            restaurant=payment.restaurant,
            payment=payment,
            invoice=invoice,  # Link to invoice
            debit_account=debit_account,
            credit_account='revenue',
            amount=amount,
            currency=payment.currency,
            reference_type='ORDER_PAYMENT',
            reference_id=invoice.id,  # Use invoice ID as reference
            entry_date=timezone.now().date(),
            value_date=timezone.now().date(),
            description=f"Payment received via {payment.get_gateway_display()} for Order {invoice.order.id}",
            created_by=payment.customer_user
        )
        
        logger.info(
            f'Accounting entry created for {payment.id} and invoice {invoice.id}',
            extra={
                'payment_id': str(payment.id),
                'invoice_id': str(invoice.id),
                'amount': float(amount),
                'debit_account': debit_account
            }
        )
    
    # Placeholder for external payment initiation
    def _initiate_momo_payment(self, payment: 'Payment', invoice: 'Invoice', user_id: str):
        """Call external API for MoMo/Card, set status to PENDING."""
        # This function would return a redirect URL or transaction token
        payment.status = 'PENDING'
        payment.save(update_fields=['status'])
        logger.info(f"Initiated external payment {payment.id} for invoice {invoice.id}")
    
    def _initiate_card_payment(self, payment: 'Payment', invoice: 'Invoice', user_id: str):
        """Call external API for MoMo/Card, set status to PENDING."""
        # This function would return a redirect URL or transaction token
        payment.status = 'PENDING'
        payment.save(update_fields=['status'])
        logger.info(f"Initiated external payment {payment.id} for invoice {invoice.id}")

    def _process_wallet_payment(self, payment: Payment, invoice: Invoice, user_id: str = None):
        """Process wallet payment - immediate completion"""
        try:
            if not payment.customer_user:
                raise Exception("Customer user required for wallet payments")
            
            wallet = CustomerWallet.objects.get(
                user=payment.customer_user,
                restaurant=payment.restaurant,
                wallet_type='PREPAID',
                status='ACTIVE'
            )
                
            if not wallet.can_afford(payment.amount):
                raise ValueError("insufficient wallet balance or wallet inactive")
            
            # Deduct funds immediately
            wallet.deduct_funds(
                amount=payment.amount,
                reference_type='ORDER_PAYMENT',
                reference_id=payment.id,
                description=f"Payment for order {invoice.order.id}"
            )
            
            # Mark as completed immediately (no collection needed)
            payment.mark_completed()
            
            # Allocate to invoice
            self._allocate_payment_to_invoice(payment, invoice, user_id)
            
            ActivityLog.objects.create(
                level='INFO',
                module='WALLET',
                action='WALLET_PAYMENT_COMPLETED',
                user_id=user_id,
                restaurant_id=payment.restaurant_id,
                details={
                    'payment_id': str(payment.id),
                    'wallet_id': str(wallet.id),
                    'amount': float(payment.amount)
                }
            )
            
            return {'message': f'Transaction on your {wallet.wallet_type} payment successfully completed.'}
        
        except CustomerWallet.DoesNotExist:
            raise Exception("Active wallet not found for customer")
  
    def _allocate_payment_to_invoice(self, payment: Payment, invoice: Invoice, user_id: str = None):
        """Allocate payment to invoice and create accounting entry"""
        
        allocation_amount = min(payment.amount, invoice.amount_due)
        
        if allocation_amount > 0:
            # Create allocation
            allocation = PaymentAllocation.objects.create(
                invoice=invoice,
                payment=payment,
                allocated_amount=allocation_amount,
                allocated_by_id=user_id
            )
            
            # Update invoice status
            invoice.mark_paid(allocation_amount)
            
            # Create accounting entry with invoice reference
            self._create_payment_accounting_entry(payment, invoice, allocation_amount, user_id)
            
            # Log allocation
            ActivityLog.objects.create(
                level='INFO',
                module='ACCOUNTING',
                action='PAYMENT_ALLOCATED',
                user_id=user_id,
                restaurant_id=payment.restaurant_id,
                details={
                    'allocation_id': str(allocation.id),
                    'payment_id': str(payment.id),
                    'invoice_id': str(invoice.id),
                    'allocated_amount': float(allocation_amount)
                }
            )
    
    
    def handle_webhook(self, webhook_data: dict, gateway: str = 'MOMO') -> dict:
        """Handle payment webhook from gateway"""
        try:
            with transaction.atomic():
                payment_id = webhook_data['external_id']
                payment = Payment.objects.get(id=payment_id)
                
                # Get invoice from existing allocations or create new allocation
                allocations = payment.allocations.select_related('invoice').all()
                
                if not allocations:
                    # If no allocation exists, find or create invoice for this payment
                    # This handles cases where payment was initiated without explicit invoice
                    invoice = self._get_or_create_invoice_for_payment(payment)
                    if invoice:
                        self._allocate_payment_to_invoice(payment, invoice, None)
                    else:
                        return {'success': False, 'error': 'No invoice found for payment'}
                else:
                    invoice = allocations[0].invoice
                
                if webhook_data['status'] == 'SUCCESSFUL':
                    payment.mark_completed(
                        gateway_reference=webhook_data['transaction_id'],
                        response_data=webhook_data
                    )
                    
                    # Update order status
                    from apps.order_processing.services import OrderProcessingService
                    order_service = OrderProcessingService()
                    order_service.update_order_status(
                        str(invoice.order.id),
                        'CONFIRMED'
                    )
                    
                    logger.info(f"Payment completed via webhook: {payment_id}")
                    
                else:
                    payment.mark_failed(f"Gateway error: {webhook_data.get('payer_message', 'Unknown error')}")
                    logger.warning(f"Payment failed via webhook: {payment_id}")
                
                return {'success': True}
                
        except Exception as e:
            logger.error(f"Webhook handling failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _get_or_create_invoice_for_payment(self, payment: Payment):
        """
        Safely get or create invoice for a payment that doesn't have one.
        Uses multiple criteria to avoid mismatching invoices.
        """
        try:
            # First, try to find the MOST LIKELY invoice using multiple criteria
            invoice = self._find_most_likely_invoice(payment)
            
            if invoice:
                logger.info(f"Found likely invoice {invoice.id} for payment {payment.id}")
                return invoice
            
            # If no likely invoice found, create a proper system invoice
            return self._create_system_invoice_for_payment(payment)
                
        except Exception as e:
            logger.error(f"Failed to get/create invoice for payment {payment.id}: {str(e)}")
            return None

    def _find_most_likely_invoice(self, payment: Payment):
        """
        Find the most likely invoice using multiple criteria with priority:
        1. Customer match + amount match + unpaid status
        2. Recent unpaid invoices with same amount
        3. Any unpaid invoice with same amount (last resort)
        """
        from apps.payment.models import Invoice
        from django.utils import timezone
        from datetime import timedelta
        
        base_queryset = Invoice.objects.filter(
            restaurant=payment.restaurant,
            status__in=['DRAFT', 'ISSUED', 'PARTIALLY_PAID'],
            total_amount=payment.amount
        )
        
        # Priority 1: Try to match by customer if payment has customer info
        if payment.customer_phone or payment.customer_email or payment.customer_user:
            customer_invoice = self._find_invoice_by_customer_match(payment, base_queryset)
            if customer_invoice:
                return customer_invoice
        
        return None

    def _find_invoice_by_customer_match(self, payment: Payment, base_queryset):
        """
        Try to match invoice by customer id with priority:
        1. User match
        """
        from apps.order_processing.models import OfflineOrder
        
        # Try customer match
        if payment.customer_user:
            try:
                customer_order = OfflineOrder.objects.filter(
                    restaurant=payment.restaurant,
                    customer_id=payment.customer_user.id,
                ).select_related('invoice').first()
                
                if customer_order and customer_order.invoice in base_queryset:
                    return customer_order.invoice
            except Exception as e:
                logger.warning(f"customer match failed for payment {payment.id}: {str(e)}")
        
        return None

    def _create_system_invoice_for_payment(self, payment: Payment):
        """
        Create a proper system invoice with clear labeling for reconciliation.
        This should be rare and indicates a payment without proper invoice association.
        """
        from apps.order_processing.models import OfflineOrder
        
        # Create a system order with clear identification
        system_order = OfflineOrder.objects.create(
            restaurant=payment.restaurant,
            local_order_id=f"SYSTEM-PAY-{payment.id.hex[:8].upper()}",
            order_items=[{
                "id": str(uuid.uuid4()),
                "name": f"Payment Reconciliation - {payment.gateway}",
                "price": str(payment.amount),
                "quantity": 1,
                "total": str(payment.amount),
                "type": "system_reconciliation"
            }],
            total_amount=payment.amount,
            tax_amount=Decimal('0.00'),
            order_status='COMPLETED',  # System orders are immediately completed
            sync_status='NOT_SYNCED',  # Don't sync system orders to external systems
            special_instructions=f"AUTO-CREATED for payment {payment.id}. Requires manual reconciliation.",
            order_type='SYS_RECONCILIATION',
            metadata={
                'system_created': True,
                'payment_id': str(payment.id),
                'payment_gateway': payment.gateway,
                'created_reason': 'payment_without_invoice',
                'requires_reconciliation': True
            }
        )
        
        # Create the system invoice
        system_invoice = Invoice.objects.create(
            order=system_order,
            restaurant=payment.restaurant,
            subtotal_amount=payment.amount,
            tax_amount=Decimal('0.00'),
            service_fee=Decimal('0.00'),
            discount_amount=Decimal('0.00'),
            total_amount=payment.amount,
            due_date=timezone.now() + timedelta(days=30),  # Long due date for reconciliation
            status='ISSUED',
            metadata={
                'system_created': True,
                'payment_id': str(payment.id),
                'reconciliation_required': True,
                'original_payment_gateway': payment.gateway
            }
        )
        
        # Log this important event
        logger.warning(
            f"Created SYSTEM invoice {system_invoice.id} for payment {payment.id}. "
            f"This indicates a payment without proper invoice association. "
            f"Manual reconciliation required. Gateway: {payment.gateway}, "
            f"Amount: {payment.amount}, Customer: {payment.customer_phone or 'Unknown'}"
        )
        
        # Create high-priority activity log for staff attention
        ActivityLog.objects.create(
            level='WARNING',
            module='PAYMENT',
            action='SYSTEM_INVOICE_CREATED',
            restaurant_id=payment.restaurant_id,
            details={
                'payment_id': str(payment.id),
                'system_invoice_id': str(system_invoice.id),
                'system_order_id': str(system_order.id),
                'amount': float(payment.amount),
                'gateway': payment.gateway,
                'customer_phone': payment.customer_phone,
                'reason': 'payment_without_invoice_association',
                'reconciliation_required': True,
                'alert_staff': True
            }
        )
        
        return system_invoice
        
        
    # method for Crypto payments
    def _initiate_crypto_payment(self, payment: 'Payment', invoice: 'Invoice', user_id: str):
        """
        Handles CRYPTO payment initiation, providing an address. 
        This acts as a pseudo-synchronous or 'offline' initiation.
        """        
        #  Using a placeholder address
        payment_address = self._get_restaurant_crypto_address(payment.currency, payment.restaurant)
        
        # Store necessary crypto details on the payment record
        payment.gateway_reference = payment_address # Storing the address/QR code link here temporarily
        payment.status = 'PENDING_CONFIRMATION'
        payment.save()
        
        # Return necessary details to the user/client
        logger.info(f"Initiated Crypto payment {payment.id} for invoice {invoice.id} to address {payment_address}")

    def _get_restaurant_crypto_address(self, currency: str, restaurant: Restaurant) -> str | None:

        
        try:
            # Use the helper method defined on the Restaurant model
            address = restaurant.get_crypto_address(currency)
            
            if not address:
                 logger.warning(f"Restaurant {restaurant} has no configured address for {currency}.")
                 return None
                 
            return address
            
        except Restaurant.DoesNotExist:
            logger.error(f"Restaurant with ID {restaurant} not found.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving crypto address for restaurant {restaurant} and currency {currency}: {e}")
            return None
    
class WalletService:
    """Service for customer wallet operations with proper accounting"""
    
    def add_funds(self, user_id: str, restaurant_id: str, amount: Decimal, 
                  reference_type: str, reference_id: str, description: str, 
                  correlation_id: str = None) -> dict:
        """Add funds to wallet with proper accounting entries and audit logging."""
        
        correlation_id = correlation_id if correlation_id else uuid.uuid4()
        
        try:
            with transaction.atomic():
                wallet, created = CustomerWallet.objects.get_or_create(
                    user_id=user_id,
                    restaurant_id=restaurant_id,
                    wallet_type='PREPAID',
                    defaults={
                        'available_balance': amount,
                        'currency': 'UGX'
                    }
                )
                
                if created:
                    # Log wallet creation
                    ActivityLog.objects.create(
                        level='INFO',
                        module='WALLET',
                        action='WALLET_CREATED',
                        user_id=user_id,
                        restaurant_id=restaurant_id,
                        correlation_id=correlation_id,
                        details={
                            'wallet_id': str(wallet.id),
                            'initial_balance': float(amount)
                        }
                    )
                else:
                    
                    if wallet.is_closed():
                        # Return specific error code to the API
                        return {'allowed': False, 'reason': 'WALLET_CLOSED', 'message': 'Wallet is permanently closed. Contact support.'}
                        
                    if wallet.is_suspended():
                        # Wallet can be viewed, but deposits might be blocked
                        return {'allowed': False, 'reason': 'WALLET_SUSPENDED', 'message': 'Wallet services are temporarily suspended.'}

                    if not wallet.is_active():
                        return {'allowed': True, 'reason': 'OK', 'message': 'Wallet is ready for deposits.'}
                        
                    wallet.add_funds(
                                amount=amount,
                                reference_type=reference_type,
                                reference_id=reference_id,
                                description=description
                            )
                        
                # Create accounting entry
                self._create_wallet_deposit_accounting_entry(
                    restaurant_id=restaurant_id,
                    amount=amount,
                    reference_id=reference_id,
                    description=description,
                    user_id=user_id
                )
                
                # Success Audit Log for Fund Addition
                if not created: # Only log addition if not a creation event
                    ActivityLog.objects.create(
                        level='INFO',
                        module='WALLET',
                        action='FUNDS_ADDED',
                        user_id=user_id,
                        restaurant_id=restaurant_id,
                        correlation_id=correlation_id,
                        details={
                            'wallet_id': str(wallet.id),
                            'amount': float(amount),
                            'ref_id': reference_id,
                            'new_balance': float(wallet.available_balance)
                        }
                    )
                
                return {
                    'success': True,
                    'wallet_id': str(wallet.id),
                    'new_balance': float(wallet.available_balance)
                }
                
        except Exception as e:
            # Failure Audit Log
            ActivityLog.objects.create(
                level='ERROR',
                module='WALLET',
                action='ADD_FUNDS_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'error': str(e), 'amount': float(amount), 'ref_id': reference_id}
            )
            logger.error(f"Failed to add funds to wallet: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _create_wallet_deposit_accounting_entry(self, restaurant_id: str, amount: Decimal, reference_id: str, description: str,user_id: str):
        """Create accounting entry for wallet deposit"""
        AccountingEntry.objects.create(
            restaurant_id=restaurant_id,
            debit_account='cash',
            credit_account='customer_deposits',  # Liability account for customer funds
            amount=amount,
            currency='UGX',
            reference_type='DEPOSIT',
            reference_id=reference_id,
            description=f"Wallet deposit: {description}",
            created_by=user_id
        )
     
    def get_wallet_balance(self, user_id, restaurant_id, wallet_type='LOYALTY'):
        """
        Retrieves the available, pending, and total balance for a specific wallet.
        """
        try:
            wallet = CustomerWallet.objects.get(
                user_id=user_id,
                restaurant_id=restaurant_id,
                wallet_type=wallet_type
            )
            
            return {
                'wallet_type': wallet.wallet_type,
                'available_balance': wallet.available_balance,
                'pending_balance': wallet.pending_balance,
                'total_balance': wallet.total_balance, # Uses the @property from the model
                'currency': wallet.currency,
                'status': wallet.status,
            }

        except CustomerWallet.DoesNotExist:
            # Handle case where the wallet doesn't exist (e.g., return zero balance or raise a specific error)
            return {
                'available_balance': 0,
                'pending_balance': 0,
                'total_balance': 0,
                'currency': 'X-SWIFT',
                'status': 'NOT_FOUND',
            }

        except Exception as e:
            # Log the error and raise or return a standard failure response
            raise e
    
    def _get_wallet_for_user(self, user_id, restaurant_id, wallet_type):
        """Helper to safely retrieve a specific wallet."""
        try:
            return CustomerWallet.objects.get(
                user_id=user_id,
                restaurant_id=restaurant_id,
                wallet_type=wallet_type
            )
        except CustomerWallet.DoesNotExist:
            logger.warning(
                f"Wallet not found for user {user_id}, restaurant {restaurant_id}, type {wallet_type}"
            )
            raise WalletError("Customer wallet not found.")

    def authorize_order_payment(self, user_id, restaurant_id, order_id, amount: Decimal, correlation_id: str = None) -> bool:
        """Orchestrates reserving funds for a new order with audit logging."""
        
        correlation_id = correlation_id if correlation_id else uuid.uuid4()
        
        try:
            amount = Decimal(amount)
            wallet = self._get_wallet_for_user(user_id, restaurant_id, wallet_type='PREPAID')
            
            wallet.authorize_funds(
                amount=amount,
                reference_type='ORDER',
                reference_id=str(order_id),
                description=f"Order authorization for #{order_id}"
            )
            
            # SUCCESS Audit Log
            ActivityLog.objects.create(
                level='INFO',
                module='WALLET',
                action='AUTHORIZATION_SUCCESS',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={
                    'wallet_id': str(wallet.id), 
                    'order_id': str(order_id), 
                    'amount': float(amount),
                    'pending_balance': float(wallet.pending_balance)
                }
            )
            logger.info(f"Authorized {amount} for order {order_id} on wallet {wallet.id}")
            return True
        
        except InsufficientFundsError as e:
            # FAILURE Audit Log (Specific Business Error)
            ActivityLog.objects.create(
                level='WARNING',
                module='WALLET',
                action='AUTHORIZATION_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'order_id': str(order_id), 'amount': float(amount), 'error': str(e)}
            )
            logger.error(f"Authorization failed for order {order_id}: {e}")
            raise e 
        except Exception as e:
            # FAILURE Audit Log (Catch-all)
            ActivityLog.objects.create(
                level='CRITICAL',
                module='WALLET',
                action='AUTHORIZATION_CRITICAL_FAILURE',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'order_id': str(order_id), 'error': str(e)}
            )
            logger.error(f"Wallet authorization failed unexpectedly for order {order_id}: {e}", exc_info=True)
            raise WalletError("An internal error occurred during authorization.")
    
    def capture_order_payment(self, user_id, restaurant_id, order_id, amount: Decimal, correlation_id: str = None) -> bool:
        """Orchestrates finalizing the payment (CAPTURE) with audit logging."""
        
        correlation_id = correlation_id if correlation_id else uuid.uuid4()
        
        try:
            amount = Decimal(amount)
            wallet = self._get_wallet_for_user(user_id, restaurant_id, wallet_type='PREPAID')
            
            wallet.capture_funds(
                amount=amount,
                reference_type='ORDER',
                reference_id=str(order_id),
                description=f"Order payment capture for #{order_id}"
            )
            
            # SUCCESS Audit Log
            ActivityLog.objects.create(
                level='INFO',
                module='WALLET',
                action='CAPTURE_SUCCESS',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={
                    'wallet_id': str(wallet.id), 
                    'order_id': str(order_id), 
                    'amount': float(amount),
                    'pending_balance_after': float(wallet.pending_balance)
                }
            )
            logger.info(f"Captured {amount} for order {order_id} on wallet {wallet.id}")
            return True
            
        except InvalidPendingCaptureError as e:
            # FAILURE Audit Log (Specific Business Error)
            ActivityLog.objects.create(
                level='ERROR',
                module='WALLET',
                action='CAPTURE_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'order_id': str(order_id), 'amount': float(amount), 'error': str(e)}
            )
            logger.warning(f"Capture failed for order {order_id} due to invalid pending amount: {e}")
            raise e
        except Exception as e:
            # FAILURE Audit Log (Catch-all)
            ActivityLog.objects.create(
                level='CRITICAL',
                module='WALLET',
                action='CAPTURE_CRITICAL_FAILURE',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'order_id': str(order_id), 'error': str(e)}
            )
            logger.error(f"Wallet capture failed unexpectedly for order {order_id}: {e}", exc_info=True)
            raise WalletError("An internal error occurred during capture.")
    
    def release_order_authorization(self, user_id, restaurant_id, order_id, amount: Decimal, correlation_id: str = None) -> bool:
        """Orchestrates releasing the reserved funds back to the customer with audit logging."""
        
        correlation_id = correlation_id if correlation_id else uuid.uuid4()
        
        try:
            amount = Decimal(amount)
            wallet = self._get_wallet_for_user(user_id, restaurant_id, wallet_type='PREPAID')
            
            wallet.release_funds(
                amount=amount,
                reference_type='ORDER_CANCEL',
                reference_id=str(order_id),
                description=f"Order cancellation funds release for #{order_id}"
            )
            
            # SUCCESS Audit Log
            ActivityLog.objects.create(
                level='INFO',
                module='WALLET',
                action='RELEASE_SUCCESS',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={
                    'wallet_id': str(wallet.id), 
                    'order_id': str(order_id), 
                    'amount': float(amount),
                    'available_balance_after': float(wallet.available_balance)
                }
            )
            logger.info(f"Released {amount} for cancelled order {order_id} on wallet {wallet.id}")
            return True
            
        except InvalidPendingCaptureError as e:
            # FAILURE Audit Log (Specific Business Error)
            ActivityLog.objects.create(
                level='ERROR',
                module='WALLET',
                action='RELEASE_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'order_id': str(order_id), 'amount': float(amount), 'error': str(e)}
            )
            logger.error(f"Release failed for order {order_id} due to invalid pending amount: {e}")
            raise e
        except Exception as e:
            # FAILURE Audit Log (Catch-all)
            ActivityLog.objects.create(
                level='CRITICAL',
                module='WALLET',
                action='RELEASE_CRITICAL_FAILURE',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'order_id': str(order_id), 'error': str(e)}
            )
            logger.error(f"Wallet release failed unexpectedly for order {order_id}: {e}", exc_info=True)
            raise WalletError("An internal error occurred during release.")
    
    def process_refund(self, user_id, restaurant_id, refund_id, amount: Decimal, original_payment_ref: str, wallet_type='PREPAID', correlation_id: str = None) -> bool:
        """
        Orchestrates crediting funds back to the customer's wallet (REFUND) with audit logging.
        """
        
        correlation_id = correlation_id if correlation_id else uuid.uuid4()
        
        try:
            amount = Decimal(amount)
            wallet = self._get_wallet_for_user(user_id, restaurant_id, wallet_type)
            
            # Call atomic model method (refund_funds)
            wallet.refund_funds(
                amount=amount,
                reference_type='REFUND',
                reference_id=str(refund_id),
                original_payment_ref=original_payment_ref,
                description=f"Processing refund ID {refund_id}"
            )
            
            # SUCCESS Audit Log
            ActivityLog.objects.create(
                level='INFO',
                module='WALLET',
                action='FUNDS_REFUNDED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={
                    'wallet_id': str(wallet.id),
                    'refund_id': str(refund_id),
                    'amount': float(amount),
                    'original_ref': original_payment_ref,
                    'new_balance': float(wallet.available_balance)
                }
            )
            
            logger.info(
                f"Successfully processed refund {refund_id} of {amount} to wallet {wallet.id}",
                extra={'user_id': user_id, 'refund_id': refund_id, 'original_ref': original_payment_ref}
            )
            return True
            
        except WalletError as e:
            # FAILURE Audit Log (Specific Business Error)
            ActivityLog.objects.create(
                level='ERROR',
                module='WALLET',
                action='REFUND_FAILED',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'refund_id': str(refund_id), 'error': str(e), 'amount': float(amount)}
            )
            logger.error(f"Refund processing failed for ID {refund_id}: {e}")
            raise e
            
        except Exception as e:
            # FAILURE Audit Log (Catch-all)
            ActivityLog.objects.create(
                level='CRITICAL',
                module='WALLET',
                action='REFUND_CRITICAL_FAILURE',
                user_id=user_id,
                restaurant_id=restaurant_id,
                correlation_id=correlation_id,
                details={'refund_id': str(refund_id), 'error': str(e), 'amount': float(amount)}
            )
            logger.error(f"Unexpected error during refund processing for ID {refund_id}: {e}", exc_info=True)
            raise WalletError("An internal error occurred during refund processing.")
    
# Service instances
invoice_service = InvoiceService()
payment_service = PaymentService()
wallet_service = WalletService()