import uuid
import secrets
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel

class OTP(TimeStampedModel):  
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('USED', 'Used'),
        ('EXPIRED', 'Expired'),
        ('REVOKED', 'Revoked'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.UUIDField(db_index=True)
    otp_code = models.CharField(max_length=6, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    expires_at = models.DateTimeField(db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'otps'
        indexes = [
            models.Index(fields=['order_id', 'status']),
            models.Index(fields=['otp_code', 'status', 'expires_at']),
            models.Index(fields=['order_id', 'status', 'otp_code'])
        ]
    
    def is_valid(self):
        if self.status != 'ACTIVE':
            return False
        if timezone.now() > self.expires_at:
            self.status = 'EXPIRED'
            self.save()
            return False
        return True
     
    def mark_used(self):
        self.status = 'USED'
        self.verified_at = timezone.now()
        self.save()
        
    def __str__(self):
        return f"OTP {self.otp_code} - {self.status}"