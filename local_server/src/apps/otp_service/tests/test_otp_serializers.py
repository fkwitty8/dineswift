from apps.otp_service.serializers import OTPGenerateSerializer, OTPVerifySerializer, OTPSerializer
from unittest.mock import patch
import pytest

@pytest.mark.django_db
class TestOTPSerializers:
    """Unit tests for OTP Serializers"""
    
    def test_otp_generate_serializer_valid(self, mock_request, test_order):
        """Test valid OTP generation serialization"""
        valid_data = {
            'order_id': str(test_order.id),  # Use actual order ID from fixture
            'expiry_minutes': 30
        }
        
        # Mock the order validation to succeed
        with patch('apps.order_processing.models.OfflineOrder') as mock_offline_order:
            mock_offline_order.objects.get.return_value = test_order
            
            serializer = OTPGenerateSerializer(data=valid_data, context={'request': mock_request})
            assert serializer.is_valid()
    
    def test_otp_generate_serializer_invalid(self, mock_request):
        """Test invalid OTP generation serialization"""
        invalid_data = {
            'order_id': 'invalid-uuid',  # Invalid UUID
            'expiry_minutes': 0  # Below minimum
        }
        
        serializer = OTPGenerateSerializer(data=invalid_data, context={'request': mock_request})
        assert not serializer.is_valid()
        assert 'order_id' in serializer.errors
        assert 'expiry_minutes' in serializer.errors
    
    def test_otp_generate_serializer_order_validation(self, mock_request):
        """Test order validation in OTP generation"""
        valid_uuid = 'a1b2c3d4-e5f6-7890-1234-567890abcdef'
        
        # Mock order validation to fail - raise the specific exception the serializer expects
        with patch('apps.order_processing.models.OfflineOrder') as mock_order:
            # Create a mock DoesNotExist exception
            class DoesNotExist(Exception):
                pass
            
            # Set up the mock to raise the specific exception
            mock_order.DoesNotExist = DoesNotExist
            mock_order.objects.get.side_effect = DoesNotExist("Order not found")
            
            serializer = OTPGenerateSerializer(
                data={'order_id': valid_uuid},
                context={'request': mock_request}
            )
            assert not serializer.is_valid()
            assert 'order_id' in serializer.errors
            assert 'Order not found' in serializer.errors['order_id'][0]
    
     
    def test_otp_verify_serializer_valid(self):
        """Test valid OTP verification serialization"""
        valid_data = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'otp_code': '123456'
        }
        
        serializer = OTPVerifySerializer(data=valid_data)
        assert serializer.is_valid()
    
    def test_otp_verify_serializer_invalid(self):
        """Test invalid OTP verification serialization"""
        # Test non-digit OTP code
        invalid_data = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'otp_code': '12a456'  # Contains letter
        }
        
        serializer = OTPVerifySerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'otp_code' in serializer.errors
        
        # Test wrong length
        invalid_data2 = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'otp_code': '12345'  # Only 5 digits
        }
        
        serializer2 = OTPVerifySerializer(data=invalid_data2)
        assert not serializer2.is_valid()
        assert 'otp_code' in serializer2.errors
    
    def test_otp_serializer_output(self, otp_instance):
        """Test OTPSerializer output format"""
        serializer = OTPSerializer(otp_instance)
        data = serializer.data
        
        expected_fields = [
            'id', 'order_id', 'otp_code', 'status',
            'expires_at', 'verified_at',
             'created_at'
        ]
        
        for field in expected_fields:
            assert field in data
        
        assert data['order_id'] == str(otp_instance.order_id)
        assert data['otp_code'] == otp_instance.otp_code
        assert data['status'] == otp_instance.status
            
    def test_otp_serializer_is_expired(self, otp_instance):
        """Test is_expired field calculation"""
        serializer = OTPSerializer(otp_instance)
        
        # Test with valid OTP
        with patch.object(otp_instance, 'is_valid', return_value=True):
            assert serializer.get_is_expired(otp_instance) is False
        
        # Test with expired OTP
        with patch.object(otp_instance, 'is_valid', return_value=False):
            assert serializer.get_is_expired(otp_instance) is True
    
    
        