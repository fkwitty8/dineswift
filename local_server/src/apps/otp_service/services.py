import secrets
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from apps.core.models import ActivityLog
from .models import OTP

logger = logging.getLogger('dineswift')

class OTPService:
  
    #Generate and verify OTPs for order pickup
    #UC-LOCAL-ORDER-102
   
    
    def __init__(self, expiry_minutes=15):
        self.expiry_minutes = expiry_minutes
    
    def generate_otp(self, order_id: str, user_id: str, restaurant_id: str) -> dict:
        """Generate a 6-digit OTP for order verification"""
        
        try:
            with transaction.atomic():
                # Invalidate any existing active OTPs for this order
                OTP.objects.filter(
                    order_id=order_id,
                    status='ACTIVE'
                ).update(status='REVOKED')
                
                # Generate secure 6-digit code
                otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
                
                expires_at = timezone.now() + timedelta(minutes=self.expiry_minutes)
                
                # Create OTP
                otp = OTP.objects.create(
                    order_id=order_id,
                    otp_code=otp_code,
                    expires_at=expires_at
                )
                
                
                ActivityLog.objects.create(
                    level='INFO',
                    module='OTP_SERVICE',
                    action='OTP_GENERATED',
                    user_id=user_id,             # Set Foreign Key field
                    restaurant_id=restaurant_id, # Set Foreign Key field
                    details={
                        'order_id': str(order_id),
                        'otp_id': str(otp.id)
                    }
                )
                
                logger.info(
                    f'OTP generated for order {order_id}',
                    extra={'order_id': order_id, 'otp_id': str(otp.id)}
                )
                
                return {
                    'otp_code': otp_code,
                    'expires_at': expires_at,
                    'otp_id': str(otp.id)
                }
                
        except Exception as e:
            logger.error(f'Failed to generate OTP: {str(e)}', exc_info=True)
            raise
    
    def verify_otp(self, order_id: str, otp_code: str, user_id: str, restaurant_id: str) -> dict:
       #Verify OTP for order pickup
        try:
            otp = OTP.objects.get(
                order_id=order_id,
                otp_code=otp_code,
                status='ACTIVE'
            )
            
            # Check if valid
            if not otp.is_valid():
                return {
                    'valid': False,
                    'message': 'OTP has expired or been revoked'
                }
            
            # Mark as used
            with transaction.atomic(): # Use a transaction for safety
                otp.mark_used()
                
                ActivityLog.objects.create(
                    level='INFO',
                    module='OTP_SERVICE',
                    action='OTP_VERIFIED',
                    # Set Foreign Key fields using the '_id' suffix
                    user_id=user_id,             
                    restaurant_id=restaurant_id, 
                    details={
                        'order_id': str(order_id),
                        'otp_id': str(otp.id)
                        # user_id and restaurant_id are now logged via the FK fields
                    }
                )
                
                logger.info(
                    f'OTP verified successfully for order {order_id}',
                    extra={'order_id': order_id}
                )
                
                return {
                    'valid': True,
                    'message': 'OTP verified successfully',
                    'verified_at': otp.verified_at.isoformat()
                }
        except OTP.DoesNotExist:
                return {
                    'valid': False,
                    'message': 'The OTP is either used, invalid, or expired'
                }       
        except Exception as e:
            logger.error(f'OTP verification error: {str(e)}', exc_info=True)
            return {
                'valid': False,
                'message': 'Verification failed',
                'error': str(e)
            }
        
    def cleanup_expired_otps(self):
        #Cleanup expired OTPs (run as scheduled task)
        
        try:
            expired_count = OTP.objects.filter(
                expires_at__lt=timezone.now(),
                status='ACTIVE'
            ).update(status='EXPIRED')
            
            logger.info(f'Cleaned up {expired_count} expired OTPs')
            return expired_count
            
        except Exception as e:
            logger.error(f'OTP cleanup failed: {str(e)}', exc_info=True)
            return 0
        
        
        
        
        
        
        
        """
OTP Service
Generate and verify OTPs for order pickup
"""
