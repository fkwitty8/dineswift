"""
Payment Monitoring Tasks
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from apps.billing.models import Payment
from apps.billing.services.payment_processor import payment_processor
from apps.billing.services.blockchain_service import BlockchainPaymentService

logger = logging.getLogger('dineswift')


@shared_task(name='apps.billing.tasks.monitor_pending_payments')
def monitor_pending_payments():
    """
    Monitor pending payments and update their status
    Runs every 2 minutes
    """
    try:
        # Get pending MoMo payments
        momo_payments = Payment.objects.filter(
            status__in=['PENDING', 'PROCESSING'],
            payment_type='MOBILE_MONEY',
            created_at__gte=timezone.now() - timedelta(hours=1)
        )
        
        momo_count = 0
        for payment in momo_payments:
            payment_processor.check_payment_status(payment)
            momo_count += 1
        
        # Get pending crypto payments
        blockchain_service = BlockchainPaymentService()
        crypto_result = blockchain_service.monitor_pending_payments()
        
        logger.info(
            f"Payment monitoring: {momo_count} MoMo, "
            f"{crypto_result['updated']} crypto updated"
        )
        
        return {
            'momo_checked': momo_count,
            'crypto_updated': crypto_result['updated'],
            'crypto_completed': crypto_result['completed']
        }
        
    except Exception as e:
        logger.error(f"Payment monitoring failed: {str(e)}", exc_info=True)
        return {'error': str(e)}


@shared_task(name='apps.billing.tasks.expire_old_payments')
def expire_old_payments():
    """
    Expire payments that weren't completed within time limit
    """
    try:
        expired_count = Payment.objects.filter(
            status='PENDING',
            expires_at__lt=timezone.now()
        ).update(status='EXPIRED')
        
        logger.info(f"Expired {expired_count} old payments")
        
        return {'expired': expired_count}
        
    except Exception as e:
        logger.error(f"Payment expiration failed: {str(e)}", exc_info=True)
        return {'error': str(e)}