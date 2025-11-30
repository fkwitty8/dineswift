import pytest
from django.utils import timezone
from datetime import timedelta
from apps.otp_service.models import OTP

@pytest.mark.django_db
class TestOTPModels:
    """Unit tests for OTP model"""
    
    def test_otp_creation(self, test_order):
        """Test creating OTP with all fields"""
        otp = OTP.objects.create(
            order_id=test_order.id,
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        
        assert otp.order_id == test_order.id
        assert otp.otp_code == '123456'
        assert otp.status == 'ACTIVE'
        assert otp.verified_at is None
        assert str(otp) == f"OTP 123456 - ACTIVE"
    
    def test_otp_is_valid_active(self, test_order):
        """Test OTP validation for active OTP"""
        otp = OTP.objects.create(
            order_id=test_order.id,
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        
        assert otp.is_valid() is True
    
    def test_otp_is_valid_expired(self, expired_otp):
        """Test OTP validation for expired OTP"""
        assert expired_otp.is_valid() is False
        expired_otp.refresh_from_db()
        assert expired_otp.status == 'EXPIRED'
    
    def test_otp_is_valid_revoked(self, revoked_otp):
        """Test OTP validation for revoked OTP"""
        assert revoked_otp.is_valid() is False
    
    def test_otp_is_valid_used(self, used_otp):
        """Test OTP validation for used OTP"""
        assert used_otp.is_valid() is False
        
    def test_otp_mark_used(self, test_order):
        """Test marking OTP as used"""
        otp = OTP.objects.create(
            order_id=test_order.id,
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        
        assert otp.verified_at is None
        assert otp.status == 'ACTIVE'
        
        otp.mark_used()
        
        assert otp.status == 'USED'
        assert otp.verified_at is not None
    
    def test_otp_model_indexes(self, test_order):
        """Test that model indexes work correctly"""
        # Create multiple OTPs with different statuses
        OTP.objects.create(
            order_id=test_order.id,
            otp_code='111111',
            expires_at=timezone.now() + timedelta(minutes=15),
            status='ACTIVE'
        )
        
        OTP.objects.create(
            order_id=test_order.id,
            otp_code='222222',
            expires_at=timezone.now() + timedelta(minutes=15),
            status='USED'
        )
        
        OTP.objects.create(
            order_id=test_order.id,
            otp_code='333333',
            expires_at=timezone.now() - timedelta(minutes=15),
            status='EXPIRED'
        )
        
        # Test queries that should use indexes
        active_otps = OTP.objects.filter(
            order_id=test_order.id,
            status='ACTIVE'
        )
        assert active_otps.count() == 1
        
        # Test combined index queries
        specific_otp = OTP.objects.filter(
            otp_code='111111',
            status='ACTIVE',
            expires_at__gt=timezone.now()
        ).first()
        assert specific_otp is not None
        
        specific_otp = OTP.objects.filter(
            order_id=test_order.id,
            otp_code='111111',
            status='ACTIVE',
            
        ).first()
        assert specific_otp is not None
    
    def test_otp_meta_options(self):
        """Test model Meta options"""
        assert OTP._meta.db_table == 'otps'
        
        # Check indexes
        index_fields = [tuple(idx.fields) for idx in OTP._meta.indexes]
        assert ('order_id', 'status') in index_fields
        assert ('otp_code', 'status', 'expires_at') in index_fields
    
    def test_otp_status_choices(self):
        """Test OTP status choices"""
        status_choices = dict(OTP.STATUS_CHOICES)
        expected_choices = {
            'ACTIVE': 'Active',
            'USED': 'Used', 
            'EXPIRED': 'Expired',
            'REVOKED': 'Revoked',
        }
        assert status_choices == expected_choices
    
    def test_otp_string_representation(self, otp_instance):
        """Test string representation of OTP"""
        expected_str = f"OTP {otp_instance.otp_code} - {otp_instance.status}"
        assert str(otp_instance) == expected_str