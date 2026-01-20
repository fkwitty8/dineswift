# serializers.py
from rest_framework import serializers
from .models import SyncQueue, ActivityLog, Restaurant
import json


class RestaurantMinimalSerializer(serializers.ModelSerializer):
    """Minimal restaurant serializer for nested relationships"""
    class Meta:
        model = Restaurant
        fields = ['id', 'name', 'supabase_restaurant_id']


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


class SyncQueueCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new sync queue items"""
    class Meta:
        model = SyncQueue
        fields = [
            'restaurant', 'sync_type', 'priority', 'payload',
            'max_retries', 'idempotency_key'
        ]
        read_only_fields = ['idempotency_key']
    
    def validate(self, data):
        # Validate sync type
        valid_sync_types = [choice[0] for choice in SyncQueue.SYNC_TYPES]
        if data.get('sync_type') not in valid_sync_types:
            raise serializers.ValidationError({
                'sync_type': f"Invalid sync type. Must be one of: {', '.join(valid_sync_types)}"
            })
        
        # Validate payload structure based on sync type
        sync_type = data.get('sync_type')
        payload = data.get('payload', {})
        
        if sync_type.startswith('ORDER_'):
            if 'local_order_id' not in payload:
                raise serializers.ValidationError({
                    'payload': "Payload must contain 'local_order_id' for order sync operations"
                })
        
        return data
    
    def create(self, validated_data):
        # Generate idempotency key if not provided
        if 'idempotency_key' not in validated_data:
            import uuid
            validated_data['idempotency_key'] = uuid.uuid4()
        
        return super().create(validated_data)


class SyncQueueUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating sync queue items"""
    class Meta:
        model = SyncQueue
        fields = [
            'status', 'priority', 'payload', 'supabase_id',
            'error_message', 'conflict_data', 'retry_count',
            'next_retry', 'last_retry'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'restaurant', 'sync_type']
    
    def validate(self, data):
        current_status = self.instance.status
        
        # Prevent updating completed items
        if current_status == 'COMPLETED' and 'status' in data and data['status'] != 'COMPLETED':
            raise serializers.ValidationError({
                'status': 'Cannot modify status of completed sync items'
            })
        
        # Prevent setting retry_count > max_retries
        if 'retry_count' in data and data['retry_count'] > self.instance.max_retries:
            raise serializers.ValidationError({
                'retry_count': f'Retry count cannot exceed max_retries ({self.instance.max_retries})'
            })
        
        return data
    
    def validate_status(self, value):
        valid_statuses = [choice[0] for choice in SyncQueue.STATUS_CHOICES]
        if value not in valid_statuses:
            raise serializers.ValidationError(
                f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        return value


class SyncQueueCancelSerializer(serializers.Serializer):
    """Serializer for cancelling sync queue items"""
    reason = serializers.CharField(required=False, max_length=500)
    force = serializers.BooleanField(default=False)
    
    def validate(self, data):
        sync_item = self.context.get('sync_item')
        
        if not sync_item:
            raise serializers.ValidationError("Sync item not found in context")
        
        # Check if item can be cancelled
        if sync_item.status not in ['PENDING', 'FAILED', 'CONFLICT']:
            if not data.get('force'):
                raise serializers.ValidationError({
                    'status': f"Cannot cancel item with status '{sync_item.status}'. Use force=True to override."
                })
        
        return data


class SyncQueueRetrySerializer(serializers.Serializer):
    """Serializer for retrying failed sync queue items"""
    immediate = serializers.BooleanField(default=False)
    max_items = serializers.IntegerField(min_value=1, max_value=1000, default=100)
    
    def validate_max_items(self, value):
        if value < 1 or value > 1000:
            raise serializers.ValidationError("max_items must be between 1 and 1000")
        return value


class SyncQueueStatsSerializer(serializers.Serializer):
    """Serializer for sync queue statistics"""
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    processing = serializers.IntegerField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    conflict = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    avg_retry_count = serializers.FloatField()
    success_rate = serializers.FloatField()


class SyncQueueMetricsSerializer(serializers.Serializer):
    """Serializer for sync queue metrics by type"""
    sync_type = serializers.CharField()
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    failed = serializers.IntegerField()
    avg_retry = serializers.FloatField()
    success_rate = serializers.SerializerMethodField()
    
    def get_success_rate(self, obj):
        total = obj['total']
        failed = obj['failed']
        completed = total - failed - obj['pending']
        return (completed / total * 100) if total > 0 else 0


class ActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for activity logs"""
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'restaurant', 'restaurant_name', 'level', 'module',
            'action', 'details', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SyncQueueBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating sync queue items"""
    items = SyncQueueCreateSerializer(many=True, write_only=True)
    
    def validate_items(self, value):
        if len(value) > 100:
            raise serializers.ValidationError("Cannot create more than 100 items at once")
        return value
    
    def create(self, validated_data):
        items_data = validated_data['items']
        created_items = []
        
        for item_data in items_data:
            # Ensure idempotency key is unique for each item
            if 'idempotency_key' not in item_data:
                import uuid
                item_data['idempotency_key'] = uuid.uuid4()
            
            serializer = SyncQueueCreateSerializer(data=item_data)
            if serializer.is_valid():
                created_item = serializer.save()
                created_items.append(created_item)
        
        return {'created': len(created_items), 'items': created_items}


class SyncQueueExportSerializer(serializers.ModelSerializer):
    """Serializer for exporting sync queue data"""
    restaurant_name = serializers.CharField(source='restaurant.name')
    restaurant_supabase_id = serializers.CharField(source='restaurant.supabase_restaurant_id')
    status_display = serializers.CharField(source='get_status_display')
    sync_type_display = serializers.CharField(source='get_sync_type_display')
    payload_size = serializers.SerializerMethodField()
    processing_time = serializers.SerializerMethodField()
    
    class Meta:
        model = SyncQueue
        fields = [
            'id', 'restaurant_name', 'restaurant_supabase_id', 'sync_type',
            'sync_type_display', 'status', 'status_display', 'priority',
            'payload_size', 'retry_count', 'max_retries', 'error_message',
            'created_at', 'updated_at', 'last_retry', 'next_retry',
            'processing_time', 'supabase_id'
        ]
    
    def get_payload_size(self, obj):
        import json
        return len(json.dumps(obj.payload))
    
    def get_processing_time(self, obj):
        if obj.status == 'COMPLETED' and obj.created_at and obj.updated_at:
            return (obj.updated_at - obj.created_at).total_seconds()
        return None