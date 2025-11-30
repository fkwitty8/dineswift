import pytest
from unittest.mock import patch, Mock
from django.db import DatabaseError

from apps.otp_service.services import OTPService
from apps.otp_service.models import OTP

from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
class TestOTPErrorHandling:
    """Error handling tests for OTP system"""
    
    def test_generate_otp_database_error(self, test_order, test_user, test_restaurant):
        """Test OTP generation when database transaction fails"""
        service = OTPService()
        
        with patch('apps.otp_service.services.transaction.atomic') as mock_atomic:
            mock_atomic.side_effect = DatabaseError("Database connection failed")
            
            with pytest.raises(DatabaseError):
                service.generate_otp(str(test_order.id), str(test_user.id), str(test_restaurant.id))
    
    def test_verify_otp_database_error(self, test_order, test_user, test_restaurant):
        """Test OTP verification when database query fails"""
        service = OTPService()
        
        with patch('apps.otp_service.models.OTP.objects.get') as mock_get:
            mock_get.side_effect = DatabaseError("Database connection failed")
            
            result = service.verify_otp(str(test_order.id), '123456', str(test_user.id), str(test_restaurant.id))
            
            assert result['valid'] is False
            assert 'Verification failed' in result['message']
    
    def test_cleanup_expired_otps_database_error(self):
        """Test cleanup when database update fails"""
        service = OTPService()
        
        with patch('apps.otp_service.models.OTP.objects.filter') as mock_filter:
            mock_filter.side_effect = DatabaseError("Database error")
            
            expired_count = service.cleanup_expired_otps()
            
            assert expired_count == 0
    
    def test_otp_is_valid_database_error(self, test_order):
        """Test OTP validation when database save fails"""
        otp = OTP.objects.create(
            order_id=test_order.id,
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        
        with patch.object(otp, 'save') as mock_save:
            mock_save.side_effect = DatabaseError("Save failed")
            
            # Should handle the error gracefully
            try:
                is_valid = otp.is_valid()
                # If we get here, the error was handled
                assert is_valid in [True, False]
            except DatabaseError:
                pytest.fail("OTP.is_valid() should handle database errors gracefully")
    
    @patch('apps.otp_service.services.logger')
    def test_generate_otp_logging_on_error(self, mock_logger, test_order, test_user, test_restaurant):
        """Test that errors are properly logged during OTP generation"""
        service = OTPService()
        
        with patch('apps.otp_service.services.transaction.atomic') as mock_atomic:
            mock_atomic.side_effect = Exception("Test error")
            
            with pytest.raises(Exception):
                service.generate_otp(str(test_order.id), str(test_user.id), str(test_restaurant.id))
            
            # Verify error was logged
            mock_logger.error.assert_called()
    
    def test_serializer_validation_database_error(self, mock_request):
        """Test serializer validation when database error occurs"""
        from apps.otp_service.serializers import OTPGenerateSerializer
        #Import the model's actual exception for mocking the side effect
        from apps.order_processing.models import OfflineOrder

        with patch('apps.order_processing.models.OfflineOrder.objects.get') as mock_get:
            # Mock the underlying ORM call to raise a non-DoesNotExist error
            # This will be caught during validation and should lead to failure.
            mock_get.side_effect = DatabaseError("Simulated database error")
            
            serializer = OTPGenerateSerializer(
                data={'order_id': '12345678-1234-5678-1234-567812345678'},
                context={'request': mock_request}
            )
            
            # The serializer's validation should fail because the get() call raises an unexpected error
            assert not serializer.is_valid()
    
    def test_view_exception_handling(self, authenticated_client, test_order):
        """Test that views properly handle exceptions"""
        with patch('apps.otp_service.views.OTPService') as MockOTPService:
            mock_service = Mock()
            mock_service.generate_otp.side_effect = Exception("Service error")
            MockOTPService.return_value = mock_service
            
            response = authenticated_client.post('/api/otp/generate/', {
                'order_id': str(test_order.id)
            })
            
            assert response.status_code == 400
            assert 'error' in response.data