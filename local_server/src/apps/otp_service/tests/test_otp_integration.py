import pytest
import uuid
from unittest.mock import patch, Mock
from django.utils import timezone
from datetime import timedelta, datetime
from rest_framework import status
from rest_framework.test import APIClient
from concurrent.futures import ThreadPoolExecutor
from django.db import connections

from apps.otp_service.models import OTP
from apps.otp_service.services import OTPService
from apps.core.models import ActivityLog

@pytest.mark.django_db
class TestOTPIntegration:
    """Integration tests for complete OTP workflow"""
    
    def test_complete_otp_workflow(self, authenticated_client, test_order):
        """Test complete OTP generation and verification workflow"""
        # Step 1: Generate OTP
        generate_data = {
            'order_id': str(test_order.id)
        }
        
        generate_response = authenticated_client.post('/api/otp/generate/', generate_data)
        assert generate_response.status_code == status.HTTP_200_OK
        
        otp_code = generate_response.data['otp_code']
        otp_id = generate_response.data['otp_id']
        
        # Verify OTP was created in database
        otp = OTP.objects.get(id=otp_id)
        assert otp.order_id == test_order.id
        assert otp.otp_code == otp_code
        assert otp.status == 'ACTIVE'
        
        # Step 2: Verify OTP with correct code
        verify_data = {
            'order_id': str(test_order.id),
            'otp_code': otp_code
        }
        
        verify_response = authenticated_client.post('/api/otp/verify/', verify_data)
        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.data['valid'] is True

        
        # Verify OTP was marked as used
        otp.refresh_from_db()
        assert otp.status == 'USED'
        assert otp.verified_at is not None
        
        # Step 3: Try to verify same OTP again (should fail)
        verify_again_response = authenticated_client.post('/api/otp/verify/', verify_data)
        assert verify_again_response.status_code == status.HTTP_200_OK
        assert verify_again_response.data['valid'] is False
        assert 'The OTP is either used, invalid' in verify_again_response.data['message']
        
        # Step 4: Generate new OTP for same order
        generate_again_response = authenticated_client.post('/api/otp/generate/', generate_data)
        assert generate_again_response.status_code == status.HTTP_200_OK
        
        # Verify old OTP is revoked and new one is active
        otp.refresh_from_db()
        assert otp.status == 'USED'# because it was used earlier and thus not active, REVOKED would be for active ones

    def test_invalid_otp_code_integration(self, authenticated_client, test_order):
        """Test verification fails with an invalid code"""
        
        # 1. Generate OTP
        generate_response = authenticated_client.post('/api/otp/generate/', {'order_id': str(test_order.id)})
        assert generate_response.status_code == status.HTTP_200_OK
        
        # 2. Attempt verification with wrong code
        verify_response = authenticated_client.post('/api/otp/verify/', {
            'order_id': str(test_order.id),
            'otp_code': '000000' # Wrong code
        })
        
        # 3. Assert failure
        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.data['valid'] is False
        assert 'The OTP is either used' in verify_response.data['message']
        
        # 4. Assert OTP status remains ACTIVE (since attempts logic is gone)
        otp = OTP.objects.get(otp_code=generate_response.data['otp_code'])
        assert otp.status == 'ACTIVE'
    
    def test_otp_expiry_integration(self, authenticated_client, test_order):
        """Test OTP expiry integration (FIXED: Timezone handling)"""
        
        # Patch timezone.now() to control time
        with patch('django.utils.timezone.now') as mock_now:
            
            # FIX: Use timezone.make_aware() to create the initial datetime object
            start_time = timezone.make_aware(datetime(2025, 1, 1, 10, 0, 0))
            mock_now.return_value = start_time
            
            generate_response = authenticated_client.post('/api/otp/generate/', {
                'order_id': str(test_order.id)
            })
            
            assert generate_response.status_code == status.HTTP_200_OK
            
            otp_code = generate_response.data['otp_code']
            
            # 2. Advance time past expiry
            expiry_time = start_time + timedelta(minutes=16)
            mock_now.return_value = expiry_time
            
            # 3. Try to verify expired OTP
            verify_response = authenticated_client.post('/api/otp/verify/', {
                'order_id': str(test_order.id),
                'otp_code': otp_code
            })
            
            # 4. Assert failure
            assert verify_response.status_code == status.HTTP_200_OK
            assert verify_response.data['valid'] is False
            assert 'expired' in verify_response.data['message'].lower()
    
    def test_activity_logging_integration(self, authenticated_client, test_order):
        """Test that activity logs are created during OTP operations"""
        initial_log_count = ActivityLog.objects.count()

        # Generate OTP
        generate_response = authenticated_client.post('/api/otp/generate/', {
            'order_id': str(test_order.id)
        })
        otp_code = generate_response.data['otp_code']

        # Verify activity log was created for generation
        generation_logs = ActivityLog.objects.filter(
            module='OTP_SERVICE',
            action='OTP_GENERATED'
        )
        assert generation_logs.count() >= 1 

        # Verify OTP
        authenticated_client.post('/api/otp/verify/', {
            'order_id': str(test_order.id),
            'otp_code': otp_code
        })

        # Verify activity log was created for verification
        verification_logs = ActivityLog.objects.filter(
            module='OTP_SERVICE',
            action='OTP_VERIFIED'
        )
        assert verification_logs.count() >= 1
   
    def test_concurrent_otp_operations(self, transactional_db, test_order, test_user):
        """Test concurrent OTP operations (Thread-safe and transaction-aware)"""
        
        results = []
        errors = []
        
        def generate_and_verify(thread_id):
            client = APIClient()
            client.force_authenticate(user=test_user)
            
            try:
                # Use the thread-local client
                generate_response = client.post('/api/otp/generate/', {
                    'order_id': str(test_order.id)
                })
                
                if generate_response.status_code == 200:
                    otp_code = generate_response.data['otp_code']
                    
                    verify_response = client.post('/api/otp/verify/', {
                        'order_id': str(test_order.id),
                        'otp_code': otp_code
                    })
                    
                    results.append((thread_id, 'success', verify_response.data.get('valid')))
                else:
                    results.append((thread_id, 'generate_failed', generate_response.status_code))
                    
            except Exception as e:
                errors.append((thread_id, e))
            
            finally:
                # Close the connection for this thread
                # This ensures the connection is released immediately after the thread finishes.
                connections['default'].close()
        
        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(generate_and_verify, i) for i in range(5)]
            
            for future in futures:
                future.result()

        #Close all remaining connections before assertions and teardown
        # This handles any connections that might have been opened by the main test thread itself.
        connections.close_all() 
        
        # Check for unexpected Python errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Assert at least one operation succeeded
        success_count = len([r for r in results if r[1] == 'success'])
        assert success_count > 0