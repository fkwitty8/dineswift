"""
Conflict Resolution System
Features:
- Multiple resolution strategies (last-write-wins, merge, custom, manual)
- Conflict detection with version vectors
- Atomic conflict resolution with rollback
- Conflict logging and analytics
- Admin intervention capabilities
"""

import logging
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime
from django.utils import timezone
from django.db import transaction, DatabaseError
from django.core.cache import cache

from apps.core.models import SyncQueue, ActivityLog
from apps.order_processing.models import OfflineOrder

logger = logging.getLogger('dineswift')


class ConflictResolutionStrategy(Enum):
    """Available conflict resolution strategies"""
    LAST_WRITE_WINS = 'last_write_wins'
    MANUAL_INTERVENTION = 'manual_intervention'
    MERGE = 'merge'
    CUSTOM_LOGIC = 'custom_logic'
    DISCARD_LOCAL = 'discard_local'
    DISCARD_REMOTE = 'discard_remote'


class ConflictDetector:
    """Detect conflicts between local and remote data"""
    
    @staticmethod
    def detect_conflict(local_data: Dict, remote_data: Dict) -> Tuple[bool, Optional[Dict]]:
        """Detect if there's a conflict between local and remote data"""
        if not local_data or not remote_data:
            return False, None
        
        # Check version vectors
        local_version = local_data.get('sync_version', 0)
        remote_version = remote_data.get('sync_version', 0)
        
        # Check timestamps
        local_updated = local_data.get('updated_at')
        remote_updated = remote_data.get('updated_at')
        
        # Check content hash
        local_hash = ConflictDetector._calculate_hash(local_data)
        remote_hash = ConflictDetector._calculate_hash(remote_data)
        
        conflict_info = {
            'detected_at': timezone.now().isoformat(),
            'local_version': local_version,
            'remote_version': remote_version,
            'local_updated': local_updated,
            'remote_updated': remote_updated,
            'local_hash': local_hash,
            'remote_hash': remote_hash,
            'fields_in_conflict': [],
        }
        
        # Compare specific fields that matter
        important_fields = ['status', 'total_amount', 'items', 'special_instructions']
        for field in important_fields:
            local_value = local_data.get(field)
            remote_value = remote_data.get(field)
            
            if local_value != remote_value:
                conflict_info['fields_in_conflict'].append({
                    'field': field,
                    'local': local_value,
                    'remote': remote_value,
                })
        
        has_conflict = (
            local_version != remote_version and 
            local_updated != remote_updated and
            len(conflict_info['fields_in_conflict']) > 0
        )
        
        return has_conflict, conflict_info if has_conflict else None
    
    @staticmethod
    def _calculate_hash(data: Dict) -> str:
        """Calculate hash for data comparison"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()
    
    @staticmethod
    def create_version_vector(data: Dict, operation: str) -> Dict:
        """Create version vector for conflict detection"""
        return {
            'version': data.get('sync_version', 0),
            'timestamp': timezone.now().isoformat(),
            'operation': operation,
            'source': 'local' if operation.startswith('LOCAL_') else 'remote',
            'checksum': ConflictDetector._calculate_hash(data),
        }


class ConflictResolver:
    """Handle conflict resolution with multiple strategies"""
    
    def __init__(self, sync_manager: 'SyncManager'):
        self.sync_manager = sync_manager
        self.default_strategy = ConflictResolutionStrategy.LAST_WRITE_WINS
    
    @transaction.atomic
    def resolve_conflict(self, sync_item: SyncQueue, strategy: str = None) -> Tuple[bool, Optional[str], Dict]:
        """
        Resolve sync conflict using specified strategy
        
        Returns:
            Tuple[bool, error_message, resolution_details]
        """
        try:
            # Get conflict data
            conflict_data = sync_item.conflict_data
            if not conflict_data:
                return False, 'No conflict data available', {}
            
            # Determine strategy
            resolution_strategy = self._get_resolution_strategy(sync_item, strategy)
            
            # Log conflict resolution attempt
            self._log_conflict_resolution_start(sync_item, resolution_strategy)
            
            # Apply resolution strategy
            resolution_methods = {
                ConflictResolutionStrategy.LAST_WRITE_WINS: self._resolve_last_write_wins,
                ConflictResolutionStrategy.MANUAL_INTERVENTION: self._resolve_manual_intervention,
                ConflictResolutionStrategy.MERGE: self._resolve_merge,
                ConflictResolutionStrategy.DISCARD_LOCAL: self._resolve_discard_local,
                ConflictResolutionStrategy.DISCARD_REMOTE: self._resolve_discard_remote,
                ConflictResolutionStrategy.CUSTOM_LOGIC: self._resolve_custom_logic,
            }
            
            resolver = resolution_methods.get(resolution_strategy, self._resolve_last_write_wins)
            success, resolution_details = resolver(sync_item, conflict_data)
            
            if success:
                # Mark conflict as resolved
                sync_item.status = 'COMPLETED'
                sync_item.conflict_data = None
                sync_item.save()
                
                # Log successful resolution
                self._log_conflict_resolution_end(
                    sync_item, 
                    resolution_strategy, 
                    success=True,
                    details=resolution_details
                )
                
                # Update conflict resolution metrics
                self._update_conflict_metrics(sync_item, resolution_strategy, success=True)
                
                return True, None, resolution_details
            else:
                # Update conflict with new strategy or mark for manual intervention
                if resolution_strategy != ConflictResolutionStrategy.MANUAL_INTERVENTION:
                    # Try manual intervention next
                    sync_item.conflict_data['resolution_attempts'].append({
                        'strategy': resolution_strategy.value,
                        'timestamp': timezone.now().isoformat(),
                        'success': False,
                        'details': resolution_details,
                    })
                    sync_item.save()
                
                # Log failed resolution
                self._log_conflict_resolution_end(
                    sync_item,
                    resolution_strategy,
                    success=False,
                    details=resolution_details
                )
                
                # Update conflict resolution metrics
                self._update_conflict_metrics(sync_item, resolution_strategy, success=False)
                
                return False, 'Conflict resolution failed', resolution_details
            
        except Exception as e:
            logger.error(f'Conflict resolution failed: {str(e)}', exc_info=True)
            return False, str(e), {}
    
    def _get_resolution_strategy(self, sync_item: SyncQueue, strategy: str = None) -> ConflictResolutionStrategy:
        """Determine which resolution strategy to use"""
        # Use specified strategy if provided
        if strategy:
            try:
                return ConflictResolutionStrategy(strategy)
            except ValueError:
                logger.warning(f'Invalid strategy {strategy}, using default')
        
        # Check if there's a preferred strategy in conflict data
        conflict_data = sync_item.conflict_data or {}
        preferred_strategy = conflict_data.get('preferred_resolution')
        if preferred_strategy:
            try:
                return ConflictResolutionStrategy(preferred_strategy)
            except ValueError:
                pass
        
        # Check business rules for strategy selection
        if self._requires_manual_intervention(sync_item):
            return ConflictResolutionStrategy.MANUAL_INTERVENTION
        
        # Default to last-write-wins for most cases
        return self.default_strategy
    
    def _requires_manual_intervention(self, sync_item: SyncQueue) -> bool:
        """Determine if conflict requires manual intervention"""
        conflict_data = sync_item.conflict_data or {}
        
        # Check for previous failed attempts
        attempts = conflict_data.get('resolution_attempts', [])
        if len(attempts) >= 3:  # Too many failed attempts
            return True
        
        # Check for critical fields in conflict
        fields_in_conflict = conflict_data.get('fields_in_conflict', [])
        critical_fields = ['total_amount', 'items', 'payment_status']
        
        for field_conflict in fields_in_conflict:
            if field_conflict.get('field') in critical_fields:
                # Check if values differ significantly
                local = field_conflict.get('local')
                remote = field_conflict.get('remote')
                
                if self._is_significant_difference(local, remote):
                    return True
        
        return False
    
    def _is_significant_difference(self, value1, value2) -> bool:
        """Check if two values differ significantly"""
        if isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
            # For monetary values, difference > 1% is significant
            if value1 == 0 or value2 == 0:
                return abs(value1 - value2) > 0.01
            return abs(value1 - value2) / max(abs(value1), abs(value2)) > 0.01
        
        # For lists/objects, any difference is significant
        return value1 != value2
    
    def _resolve_last_write_wins(self, sync_item: SyncQueue, conflict_data: Dict) -> Tuple[bool, Dict]:
        """Last-write-wins conflict resolution"""
        try:
            local_version = conflict_data.get('local_version', {})
            remote_version = conflict_data.get('remote_version', {})
            
            # Parse timestamps
            local_time = self._parse_timestamp(local_version.get('updated_at'))
            remote_time = self._parse_timestamp(remote_version.get('updated_at'))
            
            resolution_details = {
                'strategy': 'last_write_wins',
                'local_timestamp': local_version.get('updated_at'),
                'remote_timestamp': remote_version.get('updated_at'),
                'winner': None,
                'applied_changes': {},
            }
            
            if local_time > remote_time:
                # Local wins - force push
                logger.info(f'Local version wins (local: {local_time}, remote: {remote_time})')
                success = self.sync_manager._force_push_to_supabase(sync_item)
                resolution_details['winner'] = 'local'
            else:
                # Remote wins - pull and update local
                logger.info(f'Remote version wins (local: {local_time}, remote: {remote_time})')
                success = self.sync_manager._pull_from_supabase(sync_item)
                resolution_details['winner'] = 'remote'
                resolution_details['applied_changes'] = self._get_changes_applied(sync_item)
            
            return success, resolution_details
            
        except Exception as e:
            logger.error(f'Last-write-wins resolution failed: {str(e)}')
            return False, {'error': str(e)}
    
    def _resolve_merge(self, sync_item: SyncQueue, conflict_data: Dict) -> Tuple[bool, Dict]:
        """Merge conflicting changes"""
        try:
            local_version = conflict_data.get('local_version', {}).get('data', {})
            remote_version = conflict_data.get('remote_version', {}).get('data', {})
            
            # Get the order
            order_id = sync_item.payload.get('local_order_id')
            order = OfflineOrder.objects.get(id=order_id)
            
            # Merge strategy: combine non-conflicting fields, manual for conflicts
            merged_data = {}
            resolution_details = {
                'strategy': 'merge',
                'merged_fields': [],
                'conflicting_fields': [],
                'manual_intervention_required': [],
            }
            
            # Merge simple fields
            simple_fields = ['special_instructions', 'customer_notes', 'delivery_address']
            for field in simple_fields:
                local_value = local_version.get(field)
                remote_value = remote_version.get(field)
                
                if local_value == remote_value:
                    merged_data[field] = local_value
                    resolution_details['merged_fields'].append(field)
                elif local_value and not remote_value:
                    merged_data[field] = local_value
                    resolution_details['merged_fields'].append(field)
                elif remote_value and not local_value:
                    merged_data[field] = remote_value
                    resolution_details['merged_fields'].append(field)
                else:
                    # Both have different values - use local for now, flag for manual review
                    merged_data[field] = local_value
                    resolution_details['conflicting_fields'].append(field)
                    resolution_details['manual_intervention_required'].append({
                        'field': field,
                        'local': local_value,
                        'remote': remote_value,
                    })
            
            # Merge complex fields with custom logic
            merged_data['status'] = self._merge_status(local_version, remote_version)
            merged_data['items'] = self._merge_items(
                local_version.get('items', []),
                remote_version.get('items', [])
            )
            
            # Calculate merged totals
            merged_data['total_amount'] = self._calculate_total(merged_data['items'])
            
            # Update order with merged data
            for field, value in merged_data.items():
                if hasattr(order, field):
                    setattr(order, field, value)
            
            order.sync_status = 'SYNCED'
            order.sync_version += 1
            order.save()
            
            # Push merged data to Supabase
            success = self.sync_manager._force_push_merged_data(sync_item, merged_data)
            
            resolution_details['applied_merge'] = success
            resolution_details['merged_data_summary'] = {
                'status': merged_data.get('status'),
                'item_count': len(merged_data.get('items', [])),
                'total_amount': merged_data.get('total_amount'),
            }
            
            return success, resolution_details
            
        except Exception as e:
            logger.error(f'Merge resolution failed: {str(e)}', exc_info=True)
            return False, {'error': str(e)}
    
    def _resolve_manual_intervention(self, sync_item: SyncQueue, conflict_data: Dict) -> Tuple[bool, Dict]:
        """Mark conflict for manual intervention"""
        # Don't attempt to resolve, just mark for manual review
        sync_item.status = 'CONFLICT'  # Keep in conflict state
        sync_item.priority = 1  # High priority for manual review
        sync_item.save()
        
        # Create notification for manual intervention
        self._create_manual_intervention_notification(sync_item, conflict_data)
        
        return False, {
            'strategy': 'manual_intervention',
            'action': 'marked_for_review',
            'notification_created': True,
            'next_steps': 'Requires admin review',
        }
    
    def _resolve_discard_local(self, sync_item: SyncQueue, conflict_data: Dict) -> Tuple[bool, Dict]:
        """Discard local changes, keep remote"""
        try:
            success = self.sync_manager._pull_from_supabase(sync_item)
            
            return success, {
                'strategy': 'discard_local',
                'action': 'discarded_local_changes',
                'kept_remote_version': True,
            }
            
        except Exception as e:
            logger.error(f'Discard local resolution failed: {str(e)}')
            return False, {'error': str(e)}
    
    def _resolve_discard_remote(self, sync_item: SyncQueue, conflict_data: Dict) -> Tuple[bool, Dict]:
        """Discard remote changes, keep local"""
        try:
            success = self.sync_manager._force_push_to_supabase(sync_item)
            
            return success, {
                'strategy': 'discard_remote',
                'action': 'discarded_remote_changes',
                'kept_local_version': True,
            }
            
        except Exception as e:
            logger.error(f'Discard remote resolution failed: {str(e)}')
            return False, {'error': str(e)}
    
    def _resolve_custom_logic(self, sync_item: SyncQueue, conflict_data: Dict) -> Tuple[bool, Dict]:
        """Apply custom business logic for resolution"""
        # This can be extended with custom business rules
        try:
            # Example: For payment conflicts, always keep the completed payment
            if sync_item.sync_type == 'ORDER_UPDATE':
                local_data = conflict_data.get('local_version', {}).get('data', {})
                remote_data = conflict_data.get('remote_version', {}).get('data', {})
                
                local_status = local_data.get('payment_status')
                remote_status = remote_data.get('payment_status')
                
                # Business rule: Completed payment takes precedence
                if remote_status == 'COMPLETED' and local_status != 'COMPLETED':
                    return self._resolve_discard_local(sync_item, conflict_data)
                elif local_status == 'COMPLETED' and remote_status != 'COMPLETED':
                    return self._resolve_discard_remote(sync_item, conflict_data)
            
            # Fall back to last-write-wins
            return self._resolve_last_write_wins(sync_item, conflict_data)
            
        except Exception as e:
            logger.error(f'Custom logic resolution failed: {str(e)}')
            return False, {'error': str(e)}
    
    def _merge_status(self, local_data: Dict, remote_data: Dict) -> str:
        """Merge order status with business logic"""
        status_hierarchy = {
            'CANCELLED': 0,
            'FAILED': 1,
            'PENDING': 2,
            'CONFIRMED': 3,
            'PREPARING': 4,
            'READY': 5,
            'DELIVERED': 6,
            'COMPLETED': 7,
        }
        
        local_status = local_data.get('status', 'PENDING')
        remote_status = remote_data.get('status', 'PENDING')
        
        # Use the higher status (further in fulfillment)
        if status_hierarchy.get(local_status, 0) > status_hierarchy.get(remote_status, 0):
            return local_status
        return remote_status
    
    def _merge_items(self, local_items: List, remote_items: List) -> List:
        """Merge order items"""
        # Create map of items by ID
        items_map = {}
        
        # Add local items
        for item in local_items:
            item_id = item.get('item_id')
            if item_id:
                items_map[item_id] = item
        
        # Merge with remote items
        for item in remote_items:
            item_id = item.get('item_id')
            if item_id:
                if item_id in items_map:
                    # Merge quantities
                    existing = items_map[item_id]
                    existing['quantity'] = existing.get('quantity', 0) + item.get('quantity', 0)
                else:
                    items_map[item_id] = item
        
        return list(items_map.values())
    
    def _calculate_total(self, items: List) -> float:
        """Calculate total from items"""
        total = 0.0
        for item in items:
            price = item.get('price', 0)
            quantity = item.get('quantity', 1)
            total += price * quantity
        return total
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime"""
        if not timestamp_str:
            return timezone.make_aware(datetime.min)
        
        try:
            # Try ISO format
            return timezone.make_aware(datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')))
        except (ValueError, AttributeError):
            try:
                # Try other common formats
                return timezone.make_aware(datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%fZ'))
            except ValueError:
                return timezone.make_aware(datetime.min)
    
    def _get_changes_applied(self, sync_item: SyncQueue) -> Dict:
        """Get details of changes applied during resolution"""
        # This would compare before/after states
        return {
            'fields_updated': [],
            'values_changed': {},
            'timestamp': timezone.now().isoformat(),
        }
    
    def _log_conflict_resolution_start(self, sync_item: SyncQueue, strategy: ConflictResolutionStrategy):
        """Log conflict resolution start"""
        ActivityLog.objects.create(
            restaurant_id=sync_item.restaurant_id,
            level='INFO',
            module='SYNC_MANAGER',
            action='CONFLICT_RESOLUTION_STARTED',
            details={
                'sync_id': str(sync_item.id),
                'strategy': strategy.value,
                'sync_type': sync_item.sync_type,
                'conflict_data_summary': {
                    'local_version': sync_item.conflict_data.get('local_version', {}).get('version') if sync_item.conflict_data else None,
                    'remote_version': sync_item.conflict_data.get('remote_version', {}).get('version') if sync_item.conflict_data else None,
                },
            }
        )
    
    def _log_conflict_resolution_end(self, sync_item: SyncQueue, strategy: ConflictResolutionStrategy, 
                                   success: bool, details: Dict = None):
        """Log conflict resolution end"""
        ActivityLog.objects.create(
            restaurant_id=sync_item.restaurant_id,
            level='INFO' if success else 'WARNING',
            module='SYNC_MANAGER',
            action='CONFLICT_RESOLUTION_COMPLETED' if success else 'CONFLICT_RESOLUTION_FAILED',
            details={
                'sync_id': str(sync_item.id),
                'strategy': strategy.value,
                'success': success,
                'resolution_details': details or {},
                'sync_type': sync_item.sync_type,
            }
        )
    
    def _create_manual_intervention_notification(self, sync_item: SyncQueue, conflict_data: Dict):
        """Create notification for manual conflict resolution"""
        # This could be an email, Slack notification, or in-app alert
        notification_data = {
            'sync_id': str(sync_item.id),
            'restaurant_id': str(sync_item.restaurant_id),
            'sync_type': sync_item.sync_type,
            'conflict_summary': {
                'fields_in_conflict': conflict_data.get('fields_in_conflict', []),
                'local_timestamp': conflict_data.get('local_version', {}).get('updated_at'),
                'remote_timestamp': conflict_data.get('remote_version', {}).get('updated_at'),
            },
            'priority': 'high',
            'created_at': timezone.now().isoformat(),
            'requires_action': True,
        }
        
        # Store notification for admin UI
        cache_key = f'conflict_notification:{sync_item.id}'
        cache.set(cache_key, notification_data, 86400)  # 24 hours
        
        # Log notification creation
        ActivityLog.objects.create(
            restaurant_id=sync_item.restaurant_id,
            level='WARNING',
            module='SYNC_MANAGER',
            action='MANUAL_INTERVENTION_REQUESTED',
            details=notification_data
        )
    
    def _update_conflict_metrics(self, sync_item: SyncQueue, strategy: ConflictResolutionStrategy, success: bool):
        """Update conflict resolution metrics"""
        metrics_key = f'conflict_metrics:{sync_item.restaurant_id}'
        metrics = cache.get(metrics_key, {
            'total_conflicts': 0,
            'resolved_conflicts': 0,
            'failed_resolutions': 0,
            'by_strategy': {},
            'by_sync_type': {},
        })
        
        metrics['total_conflicts'] += 1
        if success:
            metrics['resolved_conflicts'] += 1
        else:
            metrics['failed_resolutions'] += 1
        
        # Update strategy metrics
        strategy_key = strategy.value
        metrics['by_strategy'][strategy_key] = metrics['by_strategy'].get(strategy_key, 0) + 1
        
        # Update sync type metrics
        sync_type = sync_item.sync_type
        metrics['by_sync_type'][sync_type] = metrics['by_sync_type'].get(sync_type, 0) + 1
        
        cache.set(metrics_key, metrics, 3600)  # 1 hour