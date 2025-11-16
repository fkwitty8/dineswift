import requests
import uuid
from django.conf import settings
from ..models import Transaction
import hashlib
import time

class PaymentGateway:
    def __init__(self, provider):
        self.provider = provider
        
    def generate_idempotency_key(self, transaction_data):
        """Generate unique idempotency key for transaction"""
        key_data = f"{transaction_data['amount']}{transaction_data['phone']}{transaction_data['reference']}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def validate_transaction(self, transaction_id, amount, phone):
        """Validate transaction with gateway"""
        if self.provider == 'mtn':
            return self._validate_mtn_transaction(transaction_id, amount, phone)
        elif self.provider == 'airtel':
            return self._validate_airtel_transaction(transaction_id, amount, phone)
        return False
    
    def _validate_mtn_transaction(self, transaction_id, amount, phone):
        """Validate MTN Mobile Money transaction"""
        headers = {
            'Authorization': f'Bearer {settings.MTN_API_KEY}',
            'X-Reference-Id': transaction_id,
            'Content-Type': 'application/json'
        }
        
        payload = {
            'amount': str(amount),
            'currency': 'UGX',
            'externalId': transaction_id,
            'payer': {'partyIdType': 'MSISDN', 'partyId': phone},
            'payerMessage': 'DineSwift Payment',
            'payeeNote': 'Restaurant Payment'
        }
        
        try:
            response = requests.post(
                f'{settings.MTN_BASE_URL}/collection/v1_0/requesttopay',
                json=payload,
                headers=headers,
                timeout=30
            )
            return response.status_code == 202
        except requests.RequestException:
            return False
    
    def _validate_airtel_transaction(self, transaction_id, amount, phone):
        """Validate Airtel Money transaction"""
        headers = {
            'Authorization': f'Bearer {settings.AIRTEL_API_KEY}',
            'Content-Type': 'application/json',
            'X-Country': 'UG',
            'X-Currency': 'UGX'
        }
        
        payload = {
            'reference': transaction_id,
            'subscriber': {'country': 'UG', 'currency': 'UGX', 'msisdn': phone},
            'transaction': {'amount': str(amount), 'id': transaction_id}
        }
        
        try:
            response = requests.post(
                f'{settings.AIRTEL_BASE_URL}/merchant/v1/payments/',
                json=payload,
                headers=headers,
                timeout=30
            )
            return response.status_code == 200
        except requests.RequestException:
            return False