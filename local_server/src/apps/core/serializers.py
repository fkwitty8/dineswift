import uuid
from rest_framework import serializers
from .models import Restaurant, ActivityLog, SyncQueue, HealthCheck

class RestaurantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = [
            'id', 'supabase_restaurant_id', 'name', 'address', 
            'contact_info', 'local_config', 'is_active', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_local_config(self, value):
        """Validate local_config JSON field"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("local_config must be a JSON object")
        return value

class ActivityLogSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'restaurant', 'restaurant_name', 'level', 'module', 'action',
            'details', 'user_id', 'correlation_id', 'ip_address', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class SyncQueueSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    sync_type_display = serializers.CharField(source='get_sync_type_display', read_only=True)
    
    class Meta:
        model = SyncQueue
        fields = [
            'id', 'restaurant', 'restaurant_name', 'sync_type', 'sync_type_display',
            'status', 'status_display', 'priority', 'payload', 'idempotency_key',
            'supabase_id', 'retry_count', 'max_retries', 'last_retry', 'next_retry',
            'error_message', 'conflict_data', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Payload must be a JSON object")
        return value

class HealthCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthCheck
        fields = ['id', 'component', 'is_healthy', 'response_time_ms', 'last_check', 'error_message']
        read_only_fields = ['id', 'last_check']