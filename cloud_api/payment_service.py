from django.conf import settings
from .models import Payment
import urllib.request
import json


class MoMoPaymentService:
    def __init__(self):
        self.api_url = getattr(settings, 'MOMO_API_URL', 'https://sandbox.momodeveloper.mtn.com')
        self.api_key = getattr(settings, 'MOMO_API_KEY', '')
        self.api_user = getattr(settings, 'MOMO_API_USER', '')
    
    def initiate_payment(self, idempotency_key, amount, phone_number, payment_type, reference_id):
        existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        
        payment = Payment.objects.create(
            idempotency_key=idempotency_key,
            payment_type=payment_type,
            reference_id=reference_id,
            amount=amount,
            phone_number=phone_number,
            status='processing'
        )
        
        try:
            data = json.dumps({
                'amount': str(amount),
                'currency': 'UGX',
                'externalId': str(reference_id),
                'payer': {'partyIdType': 'MSISDN', 'partyId': phone_number},
                'payerMessage': 'Payment',
                'payeeNote': 'Payment received'
            }).encode('utf-8')
            
            req = urllib.request.Request(
                f'{self.api_url}/collection/v1_0/requesttopay',
                data=data,
                headers={
                    'X-Reference-Id': str(payment.id),
                    'X-Target-Environment': 'sandbox',
                    'Ocp-Apim-Subscription-Key': self.api_key,
                    'Content-Type': 'application/json'
                }
            )
            
            response = urllib.request.urlopen(req)
            payment.momo_transaction_id = str(payment.id)
            payment.gateway_response = {'status_code': response.status}
            payment.status = 'completed' if response.status == 202 else 'failed'
            payment.save()
            
        except Exception as e:
            payment.status = 'failed'
            payment.gateway_response = {'error': str(e)}
            payment.save()
        
        return payment
