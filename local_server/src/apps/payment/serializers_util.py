from rest_framework import serializers
from decimal import Decimal


class ErrorResponseSerializer(serializers.Serializer):
    """Serializer for error responses"""
    success = serializers.BooleanField(default=False)
    error = serializers.CharField()
    error_code = serializers.CharField(required=False)
    details = serializers.DictField(required=False)
    correlation_id = serializers.UUIDField(required=False)


class SuccessResponseSerializer(serializers.Serializer):
    """Serializer for success responses"""
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = serializers.DictField(required=False)
    correlation_id = serializers.UUIDField(required=False)


class PaginatedResponseSerializer(serializers.Serializer):
    """Serializer for paginated responses"""
    count = serializers.IntegerField()
    next = serializers.URLField(required=False, allow_null=True)
    previous = serializers.URLField(required=False, allow_null=True)
    results = serializers.ListField()


class AmountSerializer(serializers.Serializer):
    """Serializer for amount with currency"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3, default='UGX')


class RangeFilterSerializer(serializers.Serializer):
    """Serializer for range filters"""
    min = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    max = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class DateRangeSerializer(serializers.Serializer):
    """Serializer for date range filters"""
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)


class AuditLogSerializer(serializers.Serializer):
    """Serializer for audit log entries"""
    action = serializers.CharField()
    module = serializers.CharField()
    level = serializers.CharField()
    user_id = serializers.UUIDField(required=False, allow_null=True)
    restaurant_id = serializers.UUIDField(required=False, allow_null=True)
    details = serializers.DictField()
    correlation_id = serializers.UUIDField(required=False, allow_null=True)
    timestamp = serializers.DateTimeField()