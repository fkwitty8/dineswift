import logging
from django.conf import settings
from django.utils import timezone
from apps.core.models import ActivityLog
from apps.core.services.supabase_client import supabase_client
from .models import Payment

logger = logging.getLogger('dineswift')

class PaymentService:
    """
    Implements RDD Requirements:
    - MOBILE-APP-FR-004-P1: Mobile App processes payment
    - CLOUD-FR-002-P1: Cloud Server integrates with Momo
    """
    
    def initiate_payment(self, order_data: dict, restaurant_id: str) -> dict:
        """Initiate payment process"""
        try:
            # Create payment record
            payment = Payment.objects.create(
                order_id=order_data['order_id'],
                restaurant_id=restaurant_id,
                amount=order_data['amount'],
                currency=order_data.get('currency', 'UGX'),
                gateway=order_data['payment_method'].upper(),
                customer_phone=order_data.get('customer_phone'),
                customer_email=order_data.get('customer_email'),
            )
            
            # Trigger payment processing based on gateway
            if payment.gateway == 'MOMO':
                self._initiate_momo_payment(payment)
            elif payment.gateway in ['VISA', 'MASTERCARD']:
                self._initiate_card_payment(payment)
            else:
                # Cash payment - mark as completed immediately
                payment.mark_completed()
            
            ActivityLog.objects.create(
                restaurant_id=restaurant_id,
                level='INFO',
                module='PAYMENT',
                action='PAYMENT_INITIATED',
                details={
                    'payment_id': str(payment.id),
                    'order_id': order_data['order_id'],
                    'gateway': payment.gateway,
                    'amount': float(payment.amount)
                }
            )
            
            return {
                'success': True,
                'payment_id': str(payment.id),
                'status': payment.status,
                'gateway': payment.gateway
            }
            
        except Exception as e:
            logger.error(f"Payment initiation failed: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _initiate_momo_payment(self, payment: Payment):
        """Initiate Mobile Money payment"""
        try:
            # Mark as processing
            payment.mark_processing()
            
            # In production, this would call the Momo API
            # For now, we'll simulate the API call
            logger.info(f"Simulating Momo payment for {payment.id}")
            
            # Store in Supabase for cloud processing
            supabase_data = {
                'payment_id': str(payment.id),
                'order_id': str(payment.order_id),
                'amount': float(payment.amount),
                'phone': payment.customer_phone,
                'currency': payment.currency,
                'status': 'pending'
            }
            
            response = supabase_client.table('payments').insert(supabase_data).execute()
            
            if response.data:
                logger.info(f"Momo payment initiated: {payment.id}")
            else:
                raise Exception("Failed to initiate Momo payment in Supabase")
                
        except Exception as e:
            payment.mark_failed(str(e))
            raise
    
    def _initiate_card_payment(self, payment: Payment):
        """Initiate card payment"""
        # Similar implementation for card payments
        payment.mark_processing()
        logger.info(f"Card payment initiated: {payment.id}")
    
    def get_payment_status(self, payment_id: str) -> dict:
        """Get current payment status"""
        try:
            payment = Payment.objects.get(id=payment_id)
            
            return {
                'payment_id': str(payment.id),
                'status': payment.status,
                'amount': float(payment.amount),
                'currency': payment.currency,
                'gateway': payment.gateway,
                'gateway_reference': payment.gateway_reference,
                'error_message': payment.error_message,
                'created_at': payment.created_at.isoformat(),
                'updated_at': payment.updated_at.isoformat(),
                'completed_at': payment.completed_at.isoformat() if payment.completed_at else None
            }
            
        except Payment.DoesNotExist:
            return {'error': 'Payment not found'}
        except Exception as e:
            logger.error(f"Failed to get payment status: {str(e)}")
            return {'error': 'Failed to retrieve payment status'}
    
    def handle_webhook(self, webhook_data: dict) -> dict:
        """Handle payment webhook from gateway"""
        try:
            payment_id = webhook_data['external_id']
            
            payment = Payment.objects.get(id=payment_id)
            
            if webhook_data['status'] == 'SUCCESSFUL':
                payment.mark_completed(
                    gateway_reference=webhook_data['transaction_id'],
                    response_data=webhook_data
                )
                
                # Update order status if needed
                from apps.order_processing.services import OrderProcessingService
                order_service = OrderProcessingService()
                order_service.update_order_status(
                    str(payment.order_id),
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

# Service instance
payment_service = PaymentService()