import pytest
import uuid
from decimal import Decimal
from unittest.mock import patch

from apps.otp_service.services import OTPService
from apps.otp_service.models import OTP
from django.utils import timezone
from datetime import timedelta


@pytest.mark.django_db
class TestOTPServices:
    """Unit tests for OTPService"""
    
    def test_generate_otp_success(self, test_order,test_user, test_restaurant):
        """Test successful OTP generation"""
        service = OTPService()
        
        result = service.generate_otp(str(test_order.id),str(test_user.id), str(test_restaurant.id))
        
        assert 'otp_code' in result
        assert 'expires_at' in result
        assert 'otp_id' in result
        assert len(result['otp_code']) == 6
        assert result['otp_code'].isdigit()
        
        # Verify OTP was created in database
        otp = OTP.objects.filter(order_id=test_order.id, status='ACTIVE').first()
        assert otp is not None
        assert otp.otp_code == result['otp_code']
    
    def test_generate_otp_revokes_existing(self, test_order,test_user, test_restaurant):
        """Test that generating new OTP revokes existing ones"""
        service = OTPService()
        
        # Create initial OTP
        result1 = service.generate_otp(str(test_order.id),str(test_user.id), str(test_restaurant.id))
        otp1 = OTP.objects.get(id=result1['otp_id'])
        
        # Generate new OTP for same order
        result2 = service.generate_otp(str(test_order.id),str(test_user.id), str(test_restaurant.id))
        
        # Verify first OTP is revoked
        otp1.refresh_from_db()
        assert otp1.status == 'REVOKED'
        
        # Verify new OTP is active
        otp2 = OTP.objects.get(id=result2['otp_id'])
        assert otp2.status == 'ACTIVE'
        assert otp2.otp_code != otp1.otp_code
    
    @patch('apps.otp_service.services.transaction')
    def test_generate_otp_database_error(self, mock_transaction, test_order, test_user, test_restaurant):
        """Test OTP generation when database error occurs"""
        service = OTPService()
        
        # Mock transaction to raise error
        mock_transaction.atomic.side_effect = Exception("Database connection failed")
        
        with pytest.raises(Exception):
            service.generate_otp(str(test_order.id),str(test_user.id), str(test_restaurant.id))
    
    def test_verify_otp_success(self, test_order, test_user, test_restaurant):
        """Test successful OTP verification"""
        service = OTPService()
        
        # Generate OTP first
        generate_result = service.generate_otp(str(test_order.id),str(test_user.id), str(test_restaurant.id))
        otp_code = generate_result['otp_code']
        
        # Verify the OTP
        result = service.verify_otp(str(test_order.id), otp_code, str(test_user.id), str(test_restaurant.id))
        
        assert result['valid'] is True
        assert result['message'] == 'OTP verified successfully'
        
        # Verify OTP was marked as used
        otp = OTP.objects.get(id=generate_result['otp_id'])
        assert otp.status == 'USED'
        assert otp.verified_at is not None
    
    def test_verify_otp_invalid_code(self, test_order, test_user, test_restaurant):
        """Test OTP verification with invalid code"""
        service = OTPService()
        
        # Generate OTP first
        generate_result = service.generate_otp(str(test_order.id),str(test_user.id), str(test_restaurant.id))
        
        # Try to verify with wrong code
        result = service.verify_otp(str(test_order.id), '000000', str(test_user.id), str(test_restaurant.id))
        
        assert result['valid'] is False    
        assert result['message'] == 'The OTP is either used, invalid, or expired'
    
    def test_verify_otp_expired(self, test_order,test_user, test_restaurant):
        """Test verification of expired OTP"""
        service = OTPService()
        
        # Create expired OTP manually
        otp = OTP.objects.create(
            order_id=test_order.id,
            otp_code='123456',
            expires_at='2024-01-01T12:00:00Z'  # Past date
        )
        
        result = service.verify_otp(str(test_order.id), '123456', str(test_user.id), str(test_restaurant.id))
        
        assert result['valid'] is False
        assert 'expired or been revoked' in result['message'].lower()
        
        # Verify OTP was marked as expired
        otp.refresh_from_db()
        assert otp.status == 'EXPIRED'
    
    def test_cleanup_expired_otps(self, test_order):
        """Test cleanup of expired OTPs"""
        service = OTPService()
        
        # Create expired OTP
        OTP.objects.create(
            order_id=test_order.id,
            otp_code='111111',
            expires_at='2024-01-01T12:00:00Z',  # Past date
            status='ACTIVE'
        )
        
        # Create active OTP
        active_otp = OTP.objects.create(
            order_id=test_order.id,
            otp_code='222222',
            expires_at=timezone.now() + timedelta(minutes=15),  # Future date
            status='ACTIVE'
        )
        
        expired_count = service.cleanup_expired_otps()
        
        assert expired_count == 1
        
        # Verify expired OTP was updated
        expired_otp = OTP.objects.get(otp_code='111111')
        assert expired_otp.status == 'EXPIRED'
        
        # Verify active OTP remains
        active_otp.refresh_from_db()
        assert active_otp.status == 'ACTIVE'
    
    @patch('apps.otp_service.services.timezone')
    def test_cleanup_expired_otps_error(self, mock_timezone, test_order):
        """Test cleanup when database error occurs"""
        service = OTPService()
        
        # Mock database error
        with patch('apps.otp_service.models.OTP.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")
            
            expired_count = service.cleanup_expired_otps()
            
            assert expired_count == 0