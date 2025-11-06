"""
Payment Processor Service
Integrates with Supabase Edge Functions for cloud payment processing
"""
import logging
import requests
from typing import Dict, Optional
from django.conf import settings
from django.utils import timezone

from apps.billing.models import Payment
from apps.core.services.supabase_client import supabase_client

logger = logging.getLogger('dineswift')


class PaymentProcessorService:
    """
    Process payments via Supabase Edge Functions
    """
    
    def __init__(self):
        self.supabase_url = settings.SUPABASE_CONFIG.get('url')
        self.supabase_key = settings.SUPABASE_CONFIG.get('service_key')
        self.edge_function_url = f"{self.supabase_url}/functions/v1"
    
    def process_momo_payment(self, payment: Payment) -> Dict:
        """
        Process Mobile Money payment via Supabase Edge Function
        Calls: supabase/functions/process-payment
        """
        try:
            # Update payment status
            payment.mark_processing()
            
            # Prepare payload for edge function
            payload = {
                'payment_id': str(payment.id),
            }
            
            # Call Supabase Edge Function
            response = requests.post(
                f"{self.edge_function_url}/process-payment",
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.supabase_key}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('success'):
                # Sync payment status from Supabase
                self._sync_payment_status(payment)
                
                logger.info(
                    f"MoMo payment processed successfully: {payment.id}",
                    extra={
                        'payment_id': str(payment.id),
                        'reference': result.get('reference')
                    }
                )
                
                return {
                    'success': True,
                    'reference': result.get('reference'),
                    'message': 'Payment initiated. Customer will receive USSD prompt.'
                }
            else:
                payment.mark_failed('Edge function returned error')
                return {
                    'success': False,
                    'error': 'Payment processing failed'
                }
                
        except requests.exceptions.Timeout:
            payment.mark_failed('Request timeout')
            logger.error(f"Payment processing timeout: {payment.id}")
            return {
                'success': False,
                'error': 'Payment request timed out'
            }
            
        except requests.exceptions.RequestException as e:
            payment.mark_failed(f'Network error: {str(e)}')
            logger.error(f"Payment processing error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'Network error occurred'
            }
        
        except Exception as e:
            payment.mark_failed(str(e))
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'Unexpected error occurred'
            }
    
    def _sync_payment_status(self, payment: Payment):
        """
        Sync payment status from Supabase DB
        """
        try:
            # Query Supabase for latest payment status
            response = supabase_client.client.table('payments')\
                .select('*')\
                .eq('id', str(payment.id))\
                .single()\
                .execute()
            
            if response.data:
                supabase_payment = response.data
                
                # Update local payment record
                payment.status = supabase_payment.get('status', payment.status).upper()
                payment.gateway_reference = supabase_payment.get('gateway_reference', '')
                payment.gateway_response = supabase_payment.get('gateway_response', {})
                
                if supabase_payment.get('completed_at'):
                    payment.completed_at = timezone.datetime.fromisoformat(
                        supabase_payment['completed_at'].replace('Z', '+00:00')
                    )
                
                payment.save()
                
                logger.info(f"Payment status synced: {payment.id} -> {payment.status}")
                
        except Exception as e:
            logger.error(f"Failed to sync payment status: {str(e)}", exc_info=True)
    
    def check_payment_status(self, payment: Payment) -> Dict:
        """
        Check payment status from MTN MoMo
        Called periodically to verify payment completion
        """
        try:
            # Call edge function to check status
            response = requests.post(
                f"{self.edge_function_url}/check-payment-status",
                json={'payment_id': str(payment.id)},
                headers={
                    'Authorization': f'Bearer {self.supabase_key}',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Update local payment
            self._sync_payment_status(payment)
            
            return result
            
        except Exception as e:
            logger.error(f"Status check failed: {str(e)}", exc_info=True)
            return {'error': str(e)}


class CryptoPaymentProcessor:
    """
    Process cryptocurrency payments
    (Handled locally, no edge function needed)
    """
    
    def __init__(self):
        from apps.billing.services.blockchain_service import BlockchainPaymentService
        self.blockchain_service = BlockchainPaymentService()
    
    def process_crypto_payment(self, payment: Payment, transaction_hash: str) -> Dict:
        """
        Verify and process crypto payment
        """
        try:
            success = self.blockchain_service.verify_transaction(
                payment,
                transaction_hash
            )
            
            if success:
                return {
                    'success': True,
                    'message': 'Transaction verified and processing',
                    'confirmations': payment.confirmations,
                    'required_confirmations': payment.required_confirmations
                }
            else:
                return {
                    'success': False,
                    'error': payment.error_message or 'Transaction verification failed'
                }
                
        except Exception as e:
            logger.error(f"Crypto payment processing error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instances
payment_processor = PaymentProcessorService()
crypto_processor = CryptoPaymentProcessor()