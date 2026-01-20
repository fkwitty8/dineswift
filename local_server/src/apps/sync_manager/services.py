#SYNC SERVICE

import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone
from django.db import transaction, DatabaseError
from django.conf import settings
from django.core.cache import cache

from apps.core.models import SyncQueue, ActivityLog
from apps.core.services.supabase_client import supabase_client
from apps.order_processing.models import OfflineOrder
from .conflict_resolution import ConflictResolver, ConflictDetector  # Removed unused import

logger = logging.getLogger('dineswift')


class CircuitBreaker:
    """Circuit breaker pattern for external service calls"""
    
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e
    
    def on_success(self):
        if self.state == 'HALF_OPEN':
            self.state = 'CLOSED'
        self.failure_count = 0
    
    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")


class SyncManager:
    """Production-grade synchronization manager"""
    
    def __init__(self):
        self.supabase = supabase_client
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.SYNC_CONFIG.get('circuit_breaker_threshold', 5),
            recovery_timeout=settings.SYNC_CONFIG.get('circuit_breaker_timeout', 60)
        )
        self.max_retries = settings.SYNC_CONFIG['max_retries']
        self.batch_size = settings.SYNC_CONFIG['batch_size']
        
        # Initialize conflict resolution components
        self.conflict_resolver = ConflictResolver()
        self.conflict_detector = ConflictDetector()
    
    @transaction.atomic
    def process_sync_item(self, sync_item: SyncQueue) -> Tuple[bool, Optional[str]]:
        """Process a single sync queue item with enhanced error handling"""
        try:
            # Mark as processing with optimistic locking
            updated = SyncQueue.objects.filter(
                id=sync_item.id,
                status='PENDING',
                sync_version=sync_item.sync_version
            ).update(
                status='PROCESSING',
                sync_version=sync_item.sync_version + 1
            )
            
            if not updated:
                logger.warning(f"Sync item {sync_item.id} was already processed or updated")
                return False, "Item already processed"
            
            sync_item.refresh_from_db()
            start_time = time.time()
            
            # Check for conflicts before processing
            if self._detect_and_handle_conflicts(sync_item):
                # Conflict detected and handled, don't proceed with normal sync
                return False, "Conflict detected and handled"
            
            # Route to appropriate handler
            handler_map = {
                'ORDER_CREATE': self._sync_order_create,
                'ORDER_UPDATE': self._sync_order_update,
                'ORDER_DELETE': self._sync_order_delete,
                'MENU_UPDATE': self._sync_menu_update,
                'INVENTORY_UPDATE': self._sync_inventory_update,
            }
            
            handler = handler_map.get(sync_item.sync_type)
            if not handler:
                logger.warning(f'Unknown sync type: {sync_item.sync_type}')
                self._handle_sync_failure(sync_item, f'Unknown sync type: {sync_item.sync_type}')
                return False, 'Unknown sync type'
            
            success, error_msg = handler(sync_item)
            
            if success:
                sync_item.status = 'COMPLETED'
                sync_item.error_message = ''
                sync_item.save()
                
                # Log success with timing
                duration_ms = (time.time() - start_time) * 1000
                ActivityLog.objects.create(
                    restaurant_id=sync_item.restaurant_id,
                    level='INFO',
                    module='SYNC_MANAGER',
                    action='SYNC_COMPLETED',
                    details={
                        'sync_id': str(sync_item.id),
                        'sync_type': sync_item.sync_type,
                        'duration_ms': round(duration_ms, 2),
                        'supabase_id': sync_item.supabase_id,
                    }
                )
                
                # Update metrics
                self._update_metrics(sync_item, duration_ms, success=True)
            else:
                self._handle_sync_failure(sync_item, error_msg)
                self._update_metrics(sync_item, None, success=False)
            
            return success, error_msg
            
        except DatabaseError as e:
            logger.error(f'Database error processing sync item {sync_item.id}: {str(e)}')
            self._handle_sync_failure(sync_item, f'Database error: {str(e)}')
            return False, 'Database error'
        except Exception as e:
            logger.error(
                f'Unexpected error processing sync item {sync_item.id}: {str(e)}',
                exc_info=True
            )
            self._handle_sync_failure(sync_item, f'Unexpected error: {str(e)}')
            return False, 'Unexpected error'
    
    def process_batch(self, sync_items: List[SyncQueue]) -> Dict[str, int]:
        """Process multiple sync items in batch"""
        results = {
            'total': len(sync_items),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
        }
        
        for item in sync_items:
            try:
                success, _ = self.process_sync_item(item)
                if success:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                logger.error(f"Failed to process batch item {item.id}: {str(e)}")
                results['failed'] += 1
        
        return results
    
    def _sync_order_create(self, sync_item: SyncQueue) -> Tuple[bool, Optional[str]]:
        """Sync new order to Supabase with circuit breaker"""
        try:
            payload = sync_item.payload
            order_id = payload.get('local_order_id')
            
            if not order_id:
                return False, 'Missing local_order_id in payload'
            
            # Get local order with lock
            try:
                order = OfflineOrder.objects.select_for_update().get(
                    id=order_id,
                    restaurant_id=sync_item.restaurant_id
                )
            except OfflineOrder.DoesNotExist:
                return False, f'Order {order_id} not found'
            
            # Prepare data for Supabase
            supabase_data = {
                'local_order_id': order.local_order_id,
                'restaurant_id': str(order.restaurant.supabase_restaurant_id),
                'table_id': str(order.table_id) if order.table_id else None,
                'customer_id': str(order.customer_id) if order.customer_id else None,
                'items': order.order_items,
                'total_amount': float(order.total_amount),
                'tax_amount': float(order.tax_amount),
                'status': order.order_status,
                'special_instructions': order.special_instructions,
                'created_at': order.created_at.isoformat(),
                'metadata': payload.get('metadata', {}),
            }
            
            # Sync to Supabase with circuit breaker
            try:
                supabase_id = self.circuit_breaker.call(
                    self.supabase.sync_order,
                    supabase_data
                )
            except Exception as e:
                logger.error(f'Supabase sync failed: {str(e)}')
                return False, f'Supabase error: {str(e)}'
            
            if supabase_id:
                # Update local order with Supabase ID
                order.supabase_order_id = supabase_id
                order.sync_status = 'SYNCED'
                order.sync_version += 1
                order.save()
                
                sync_item.supabase_id = supabase_id
                return True, None
            
            return False, 'Failed to sync to Supabase'
            
        except Exception as e:
            logger.error(f'Order create sync failed: {str(e)}', exc_info=True)
            return False, str(e)
    
    def _sync_order_update(self, sync_item: SyncQueue) -> Tuple[bool, Optional[str]]:
        """Sync order updates to Supabase"""
        try:
            payload = sync_item.payload
            order_id = payload.get('local_order_id')
            supabase_order_id = payload.get('supabase_order_id')
            updates = payload.get('updates', {})
            
            if not supabase_order_id:
                return False, 'No Supabase order ID for update'
            
            # Verify order exists and belongs to restaurant
            try:
                order = OfflineOrder.objects.get(
                    id=order_id,
                    restaurant_id=sync_item.restaurant_id,
                    supabase_order_id=supabase_order_id
                )
            except OfflineOrder.DoesNotExist:
                return False, f'Order {order_id} not found or mismatched Supabase ID'
            
            # Update in Supabase with circuit breaker
            try:
                success = self.circuit_breaker.call(
                    self.supabase.update_order,
                    supabase_order_id,
                    updates
                )
            except Exception as e:
                logger.error(f'Supabase update failed: {str(e)}')
                return False, f'Supabase error: {str(e)}'
            
            if success:
                # Update local status
                order.sync_status = 'SYNCED'
                order.sync_version += 1
                order.save()
                return True, None
            
            return False, 'Failed to update order in Supabase'
            
        except Exception as e:
            logger.error(f'Order update sync failed: {str(e)}', exc_info=True)
            return False, str(e)
    
    def _sync_order_delete(self, sync_item: SyncQueue) -> Tuple[bool, Optional[str]]:
        """Handle order deletion sync"""
        # Implementation for order deletion
        return False, 'Not implemented'
    
    def _sync_menu_update(self, sync_item: SyncQueue) -> Tuple[bool, Optional[str]]:
        """Handle menu update sync"""
        # Implementation for menu updates
        return False, 'Not implemented'
    
    def _sync_inventory_update(self, sync_item: SyncQueue) -> Tuple[bool, Optional[str]]:
        """Handle inventory update sync"""
        # Implementation for inventory updates
        return False, 'Not implemented'
    
    def _handle_sync_failure(self, sync_item: SyncQueue, error_msg: str):
        """Handle sync failure with enhanced retry logic"""
        sync_item.mark_retry(error_msg[:1000])
        
        # Log failure
        ActivityLog.objects.create(
            restaurant_id=sync_item.restaurant_id,
            level='WARNING' if sync_item.can_retry() else 'ERROR',
            module='SYNC_MANAGER',
            action='SYNC_FAILED',
            details={
                'sync_id': str(sync_item.id),
                'sync_type': sync_item.sync_type,
                'retry_count': sync_item.retry_count,
                'error': error_msg[:500],
                'next_retry': sync_item.next_retry.isoformat() if sync_item.next_retry else None,
            }
        )
    
    def _update_metrics(self, sync_item: SyncQueue, duration_ms: Optional[float], success: bool):
        """Update sync metrics in cache"""
        cache_key = f'sync_metrics:{sync_item.restaurant_id}:{sync_item.sync_type}'
        metrics = cache.get(cache_key, {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'total_duration': 0,
        })
        
        metrics['total'] += 1
        if success:
            metrics['successful'] += 1
            if duration_ms:
                metrics['total_duration'] += duration_ms
        else:
            metrics['failed'] += 1
        
        cache.set(cache_key, metrics, 3600)  # Store for 1 hour
    
    def get_sync_metrics(self, restaurant_id: str, sync_type: str = None) -> Dict[str, Any]:
        """Get sync metrics for restaurant"""
        if sync_type:
            cache_key = f'sync_metrics:{restaurant_id}:{sync_type}'
            return cache.get(cache_key, {})
        else:
            # Aggregate all sync types
            metrics = {}
            sync_types = [choice[0] for choice in SyncQueue.SYNC_TYPES]
            for st in sync_types:
                cache_key = f'sync_metrics:{restaurant_id}:{st}'
                type_metrics = cache.get(cache_key)
                if type_metrics:
                    metrics[st] = type_metrics
            return metrics 
        
    def _detect_and_handle_conflicts(self, sync_item: SyncQueue) -> bool:
        """Detect and handle conflicts before sync"""
        try:
            if sync_item.sync_type == 'ORDER_UPDATE':
                order_id = sync_item.payload.get('local_order_id')
                supabase_order_id = sync_item.payload.get('supabase_order_id')
                
                if supabase_order_id:
                    # Get remote version from Supabase
                    remote_order = self.supabase.get_order(supabase_order_id)
                    
                    if remote_order:
                        # Get local order
                        local_order = OfflineOrder.objects.get(id=order_id)
                        
                        # Convert to comparable format
                        local_data = self._prepare_order_data(local_order)
                        remote_data = self._prepare_order_data_from_remote(remote_order)
                        
                        # Detect conflict
                        has_conflict, conflict_info = self.conflict_detector.detect_conflict(
                            local_data, remote_data
                        )
                        
                        if has_conflict:
                            # Mark as conflict and store conflict data
                            sync_item.status = 'CONFLICT'
                            sync_item.conflict_data = {
                                'detected_at': timezone.now().isoformat(),
                                'local_version': {
                                    'data': local_data,
                                    'updated_at': local_order.updated_at.isoformat(),
                                    'sync_version': local_order.sync_version,
                                },
                                'remote_version': {
                                    'data': remote_data,
                                    'updated_at': remote_order.get('updated_at'),
                                    'sync_version': remote_order.get('sync_version', 0),
                                },
                                'conflict_info': conflict_info,
                                'resolution_attempts': [],
                            }
                            sync_item.save()
                            
                            # Log conflict detection
                            ActivityLog.objects.create(
                                restaurant_id=sync_item.restaurant_id,
                                level='WARNING',
                                module='SYNC_MANAGER',
                                action='CONFLICT_DETECTED',
                                details={
                                    'sync_id': str(sync_item.id),
                                    'sync_type': sync_item.sync_type,
                                    'conflict_summary': conflict_info,
                                }
                            )
                            
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f'Conflict detection failed: {str(e)}')
            return False
    
    def resolve_conflict(self, sync_item: SyncQueue, strategy: str = None) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Resolve sync conflict using the enhanced resolver"""
        return self.conflict_resolver.resolve_conflict(sync_item, strategy)
    
    def _force_push_to_supabase(self, sync_item: SyncQueue) -> bool:
        """Force push local version to Supabase"""
        # Override any version checks
        if sync_item.sync_type == 'ORDER_UPDATE':
            # Get the order
            order_id = sync_item.payload.get('local_order_id')
            order = OfflineOrder.objects.get(id=order_id)
            
            # Prepare data with force flag
            updates = sync_item.payload.get('updates', {})
            updates['_force_sync'] = True  # Add force flag
            updates['sync_version'] = order.sync_version + 1
            
            # Update in Supabase with force
            success = self.supabase.update_order(
                order.supabase_order_id,
                updates
            )
            
            if success:
                order.sync_status = 'SYNCED'
                order.sync_version += 1
                order.save()
                
                return True
            
            return False
        
        # For other sync types, use normal processing
        success, error = self.process_sync_item(sync_item)
        return success
    
    def _force_push_merged_data(self, sync_item: SyncQueue, merged_data: Dict[str, Any]) -> bool:
        """Force push merged data to Supabase"""
        try:
            if sync_item.sync_type == 'ORDER_UPDATE':
                supabase_order_id = sync_item.payload.get('supabase_order_id')
                
                if supabase_order_id:
                    # Update with merged data
                    success = self.supabase.update_order(supabase_order_id, merged_data)
                    
                    if success:
                        # Update local order to match
                        order_id = sync_item.payload.get('local_order_id')
                        order = OfflineOrder.objects.get(id=order_id)
                        
                        for field, value in merged_data.items():
                            if hasattr(order, field):
                                setattr(order, field, value)
                        
                        order.sync_status = 'SYNCED'
                        order.sync_version += 1
                        order.save()
                        
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f'Force push merged data failed: {str(e)}')
            return False
    
    def _pull_from_supabase(self, sync_item: SyncQueue) -> bool:
        """Pull remote version and update local with comprehensive field mapping"""
        try:
            order_id = sync_item.payload.get('local_order_id')
            order = OfflineOrder.objects.get(id=order_id)
            
            # Fetch latest from Supabase
            remote_order = self.supabase.get_order(order.supabase_order_id)
            
            if remote_order:
                # Map remote fields to local model
                field_mapping = {
                    'status': 'order_status',
                    'items': 'order_items',
                    'total_amount': 'total_amount',
                    'tax_amount': 'tax_amount',
                    'special_instructions': 'special_instructions',
                    'customer_id': 'customer_id',
                    'table_id': 'table_id',
                }
                
                # Apply updates
                for remote_field, local_field in field_mapping.items():
                    if remote_field in remote_order:
                        remote_value = remote_order[remote_field]
                        current_value = getattr(order, local_field)
                        
                        # Only update if changed
                        if remote_value != current_value:
                            setattr(order, local_field, remote_value)
                
                # Update metadata
                order.sync_status = 'SYNCED'
                order.sync_version = remote_order.get('sync_version', order.sync_version + 1)
                order.updated_at = timezone.now()
                order.save()
                
                # Log the pull operation
                ActivityLog.objects.create(
                    restaurant_id=sync_item.restaurant_id,
                    level='INFO',
                    module='SYNC_MANAGER',
                    action='REMOTE_PULL_COMPLETED',
                    details={
                        'sync_id': str(sync_item.id),
                        'order_id': str(order.id),
                        'fields_updated': list(field_mapping.keys()),
                        'remote_sync_version': remote_order.get('sync_version'),
                    }
                )
                
                return True
            
            return False
            
        except OfflineOrder.DoesNotExist:
            logger.error(f'Local order {order_id} not found')
            return False
        except Exception as e:
            logger.error(f'Pull from Supabase failed: {str(e)}', exc_info=True)
            return False
    
    def _prepare_order_data(self, order) -> Dict[str, Any]:
        """Prepare order data for conflict detection"""
        return {
            'id': str(order.id),
            'status': order.order_status,
            'items': order.order_items,
            'total_amount': float(order.total_amount),
            'tax_amount': float(order.tax_amount),
            'special_instructions': order.special_instructions,
            'sync_version': order.sync_version,
            'updated_at': order.updated_at.isoformat(),
        }
    
    def _prepare_order_data_from_remote(self, remote_order: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare remote order data for conflict detection"""
        return {
            'id': remote_order.get('id'),
            'status': remote_order.get('status'),
            'items': remote_order.get('items', []),
            'total_amount': float(remote_order.get('total_amount', 0)),
            'tax_amount': float(remote_order.get('tax_amount', 0)),
            'special_instructions': remote_order.get('special_instructions'),
            'sync_version': remote_order.get('sync_version', 0),
            'updated_at': remote_order.get('updated_at'),
        }
    
    def get_conflict_metrics(self, restaurant_id: str = None) -> Dict[str, Any]:
        """Get conflict resolution metrics"""
        if restaurant_id:
            key = f'conflict_metrics:{restaurant_id}'
        else:
            key = 'conflict_metrics:global'
        
        return cache.get(key, {})