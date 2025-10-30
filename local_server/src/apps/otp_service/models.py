import uuid
import secrets
from django.db import models
from django.utils import timezone
from datetime import timedelta
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
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)
    
    class Meta:
        db_table = 'otps'
        indexes = [
            models.Index(fields=['order_id', 'status']),
            models.Index(fields=['otp_code', 'status', 'expires_at']),
        ]
    
    def is_valid(self):
        if self.status != 'ACTIVE':
            return False
        if timezone.now() > self.expires_at:
            self.status = 'EXPIRED'
            self.save()
            return False
        if self.attempts >= self.max_attempts:
            self.status = 'REVOKED'
            self.save()
            return False
        return True
    
    def increment_attempts(self):
        self.attempts += 1
        if self.attempts >= self.max_attempts:
            self.status = 'REVOKED'
        self.save()
    
    def mark_used(self):
        self.status = 'USED'
        self.verified_at = timezone.now()
        self.save()