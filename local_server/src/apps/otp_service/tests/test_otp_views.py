import pytest
import json
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APIClient
from apps.otp_service.models import OTP

@pytest.mark.django_db
class TestOTPViews:
    
    @patch('apps.otp_service.services.OTPService.generate_otp')
    def test_generate_otp_success(self, mock_generate, authenticated_client, test_order):
        """Test successful OTP generation via API"""
        mock_generate.return_value = {
            'otp_code': '123456',
            'expires_at': '2025-11-25T03:15:00Z',
            'otp_id': 'test-otp-id'
        }
        
        data = {
            'order_id': str(test_order.id)
        }
        
        response = authenticated_client.post('/api/otp/generate/', data)
     
        if response.status_code == 500:
            print("500 Error Response:", response.data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['otp_code'] == '123456'
        assert 'otp_id' in response.data
    
    @patch('apps.otp_service.services.OTPService.generate_otp')
    def test_generate_otp_failure(self, mock_generate, authenticated_client, test_order):
        """Test failed OTP generation via API"""
        mock_generate.side_effect = Exception("Generation failed")
        
        data = {
            'order_id': str(test_order.id)
        }
        
        response = authenticated_client.post('/api/otp/generate/', data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
    
    def test_generate_otp_unauthorized(self):
        """Test unauthorized access to generate OTP"""
        client = APIClient()
        response = client.post('/api/otp/generate/', {})
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @patch('apps.otp_service.services.OTPService.verify_otp')
    def test_verify_otp_success(self, mock_verify, authenticated_client, test_order):
        """Test successful OTP verification via API"""
        mock_verify.return_value = {
            'valid': True,
            'message': 'OTP verified successfully',
            'verified_at': '2024-01-01T12:00:00Z'
        }
        
        data = {
            'order_id': str(test_order.id),
            'otp_code': '123456'
        }
        
        response = authenticated_client.post('/api/otp/verify/', data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['valid'] is True
        assert 'verified_at' in response.data
    
    @patch('apps.otp_service.services.OTPService.verify_otp')
    def test_verify_otp_failure(self, mock_verify, authenticated_client, test_order):
        """Test failed OTP verification via API"""
        mock_verify.return_value = {
            'valid': False,
            'message': 'Invalid OTP'
        }
        
        data = {
            'order_id': str(test_order.id),
            'otp_code': '000000'
        }
        
        response = authenticated_client.post('/api/otp/verify/', data,format='json')
        
        assert response.status_code == status.HTTP_200_OK  # Still 200, but valid=false
        assert response.data['valid'] is False
    
    @patch('apps.otp_service.services.OTPService.verify_otp')
    def test_verify_otp_service_error(self, mock_verify, authenticated_client, test_order):
        """Test OTP verification when service raises error"""
        mock_verify.side_effect = Exception("Verification failed")
        
        data = {
            'order_id': str(test_order.id),
            'otp_code': '123456'
        }
        
        response = authenticated_client.post('/api/otp/verify/', data,format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
    
    def test_get_order_otp_success(self, authenticated_client, test_order, otp_instance):
        """Test successful retrieval of order OTP"""
        response = authenticated_client.get(f'/api/otp/order/{test_order.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['otp_code'] == otp_instance.otp_code
        assert response.data['order_id'] == str(otp_instance.order_id)
    
    def test_get_order_otp_not_found(self, authenticated_client, test_order):
        """Test retrieval when no OTP exists for order"""
        response = authenticated_client.get(f'/api/otp/order/{test_order.id}/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
    
    def test_get_order_otp_order_not_found(self, authenticated_client):
        """Test retrieval when order doesn't exist"""
        fake_order_id = '00000000-0000-0000-0000-000000000000'
        response = authenticated_client.get(f'/api/otp/order/{fake_order_id}/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'error' in response.data
    
    def test_get_order_otp_unauthorized(self):
        """Test unauthorized access to order OTP"""
        client = APIClient()
        # FIX: Use a string that LOOKS like a UUID so the URL resolver matches
        valid_uuid_format = '00000000-0000-0000-0000-000000000001' 
        response = client.get(f'/api/otp/order/{valid_uuid_format}/')
        
        # Now it will pass the URL resolver and fail at the permission check
        assert response.status_code == status.HTTP_403_FORBIDDEN