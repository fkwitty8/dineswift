"""
V1 Serializers - Legacy Mobile App Compatibility
Inherits from global base serializers
"""
from rest_framework import serializers
from apps.menu_cache.serializers import (
    BaseMenuItemSerializer,
    BaseMenuCategorySerializer,
    BaseMenuCacheSerializer,
    BaseMenuSyncSerializer,
    get_categories_data
)


class MenuItemV1Serializer(BaseMenuItemSerializer):
    """V1-specific menu item fields for legacy mobile app"""
    # Inherits all base fields and adds legacy-specific ones
    item_code = serializers.CharField(required=False, help_text="Legacy item code for mobile app")
    tax_rate = serializers.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.0,
        help_text="Tax rate for legacy calculations"
    )
    discount_eligible = serializers.BooleanField(
        default=False,
        help_text="Whether item is eligible for legacy discounts"
    )
    
    # Override base field with V1-specific options
    description = serializers.CharField(
        required=False, 
        allow_blank=True,
        max_length=200,  # V1 has character limit
        help_text="Short description for mobile display"
    )


class MenuCategoryV1Serializer(BaseMenuCategorySerializer):
    """V1-specific category with legacy mobile structure"""
    # Add V1-specific fields
    display_order = serializers.IntegerField(
        default=0,
        help_text="Display order for mobile app"
    )
    icon_name = serializers.CharField(
        required=False, 
        allow_blank=True,
        help_text="Icon name for mobile app UI"
    )
    
    # Use V1 item serializer
    items = MenuItemV1Serializer(many=True)


class MenuCacheV1Serializer(BaseMenuCacheSerializer):
    """V1 serializer for MenuCache with legacy compatibility"""
    # Add V1-specific fields
    categories = serializers.SerializerMethodField()
    legacy_support = serializers.SerializerMethodField()
    
    class Meta(BaseMenuCacheSerializer.Meta):
        # Extend base fields
        fields = BaseMenuCacheSerializer.Meta.fields + ['categories', 'legacy_support']
    
    def get_categories(self, obj):
        """Use V1 category serializer"""
        return get_categories_data(obj, MenuCategoryV1Serializer)
    
    def get_legacy_support(self, obj):
        """Add legacy compatibility info"""
        return {
            'supports_mobile_v1': True,
            'api_version': '1.0',
            'requires_item_codes': True,
            'max_image_size': '500kb'  # Legacy mobile limitation
        }


class MenuSyncV1Serializer(BaseMenuSyncSerializer):
    """V1-specific sync serializer"""
    # Add V1-specific fields
    sync_mode = serializers.ChoiceField(
        choices=['incremental', 'full'],
        default='incremental',
        help_text="Sync mode for legacy system"
    )
    include_archived = serializers.BooleanField(
        default=False,
        help_text="Include archived items (legacy behavior)"
    )
    
    # Override validation for V1
    def validate(self, attrs):
        attrs = super().validate(attrs)
        
        # V1-specific validation
        if attrs.get('sync_mode') == 'full':
            # Full sync requires confirmation in V1
            if not self.context.get('request').data.get('confirm_full_sync'):
                raise serializers.ValidationError({
                    'confirm_full_sync': 'Full sync requires confirmation for legacy system'
                })
        
        return attrs