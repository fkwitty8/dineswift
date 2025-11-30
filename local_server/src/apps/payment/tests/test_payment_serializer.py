import pytest
from unittest.mock import patch
from apps.payment.serializers import (
    PaymentInitiateSerializer, 
    PaymentStatusSerializer,
    PaymentWebhookSerializer
)
from apps.payment.models import Payment

@pytest.mark.django_db
class TestPaymentSerializers:
    """Unit tests for Payment Serializers"""
    
    def test_payment_initiate_serializer_valid(self):
        """Test valid payment initiation serialization"""
        valid_data = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'amount': '100.00',
            'currency': 'UGX',
            'payment_method': 'momo',
            'customer_phone': '256712345678',
            'customer_email': 'test@example.com'
        }
        
        serializer = PaymentInitiateSerializer(data=valid_data)
        assert serializer.is_valid()
    
    def test_payment_initiate_serializer_momo_phone_required(self):
        """Test Momo payment requires phone number"""
        invalid_data = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'amount': '100.00',
            'payment_method': 'momo'
            # Missing customer_phone
        }
        
        serializer = PaymentInitiateSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'customer_phone' in serializer.errors
    
    def test_payment_initiate_serializer_phone_format_validation(self):
        """Test phone number format validation for Momo"""
        invalid_data = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'amount': '100.00',
            'payment_method': 'momo',
            'customer_phone': '0712345678'  # Wrong format
        }
        
        serializer = PaymentInitiateSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'customer_phone' in serializer.errors
    
    def test_payment_initiate_serializer_min_amount(self):
        """Test minimum amount validation"""
        invalid_data = {
            'order_id': '12345678-1234-5678-1234-567812345678',
            'amount': '0.00',  # Below minimum
            'payment_method': 'cash'
        }
        
        serializer = PaymentInitiateSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'amount' in serializer.errors
    
    def test_payment_status_serializer_output(self, payment_instance):
        """Test PaymentStatusSerializer output format"""
        serializer = PaymentStatusSerializer(payment_instance)
        data = serializer.data
        
        expected_fields = [
            'id', 'status', 'amount', 'currency',
            'gateway_reference', 'error_message', 
            'created_at', 'updated_at', 'completed_at'
        ]
        
        for field in expected_fields:
            assert field in data
        
        assert data['id'] == str(payment_instance.id)
        assert data['status'] == payment_instance.status
        assert data['amount'] == str(payment_instance.amount)
    
    def test_payment_webhook_serializer_valid(self, payment_instance):
        """Test valid webhook serialization"""
        valid_data = {
            'transaction_id': 'TXN123456',
            'status': 'SUCCESSFUL',
            'amount': '100.00',
            'currency': 'UGX',
            'payer_message': 'Payment successful',
            'external_id': str(payment_instance.id)
        }
        
        serializer = PaymentWebhookSerializer(data=valid_data)
        assert serializer.is_valid()
    
    def test_payment_webhook_serializer_invalid_status(self):
        """Test webhook validation with invalid status"""
        invalid_data = {
            'transaction_id': 'TXN123456',
            'status': 'INVALID_STATUS',  # Invalid choice
            'amount': '100.00',
            'currency': 'UGX',
            'external_id': '12345678-1234-5678-1234-567812345678'
        }
        
        serializer = PaymentWebhookSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'status' in serializer.errors
    
    def test_payment_webhook_serializer_external_id_validation(self):
        """Test external_id validation in webhook"""
        invalid_data = {
            'transaction_id': 'TXN123456',
            'status': 'SUCCESSFUL',
            'amount': '100.00',
            'currency': 'UGX',
            'external_id': '00000000-0000-0000-0000-000000000000'  # Non-existent
        }
        
        serializer = PaymentWebhookSerializer(data=invalid_data)
        assert not serializer.is_valid()
        assert 'external_id' in serializer.errors