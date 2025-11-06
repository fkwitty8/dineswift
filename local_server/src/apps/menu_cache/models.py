"""
Menu Cache Models
Handles local caching of restaurant menus
"""
import uuid
import hashlib
import json
from django.db import models
from django.db.models import JSONField
from apps.core.models import TimeStampedModel, Restaurant


class MenuCache(TimeStampedModel):
    """
    Local cache of restaurant menus from Supabase
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE)
    menu_data = JSONField()
    version = models.IntegerField(default=1)
    checksum = models.CharField(max_length=64)  # SHA-256
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_cache'
        indexes = [
            models.Index(fields=['restaurant', 'is_active']),
            models.Index(fields=['checksum']),
        ]
        unique_together = ['restaurant', 'version']
    
    def calculate_checksum(self):
        """Calculate SHA-256 checksum for data integrity"""
        menu_string = json.dumps(self.menu_data, sort_keys=True)
        return hashlib.sha256(menu_string.encode()).hexdigest()
    
    def save(self, *args, **kwargs):
        if not self.checksum:
            self.checksum = self.calculate_checksum()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Menu v{self.version} - {self.restaurant.name}"