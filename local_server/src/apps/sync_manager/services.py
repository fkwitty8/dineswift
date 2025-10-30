#SYNC SERVICE


import logging
from typing import Optional, Dict
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from apps.core.models import SyncQueue, ActivityLog
from apps.core.services.supabase_client import supabase_client
from apps.order_processing.models import OfflineOrder

logger = logging.getLogger('dineswift')

class SyncManager:
   #Manages synchronization between local DB and Supabase
    
    
    def __init__(self):
        self.supabase = supabase_client
        self.max_retries = settings.SYNC_CONFIG['max_retries']
    
    @transaction.atomic
    def process_sync_item(self, sync_item: SyncQueue) -> bool:
        #Process a single sync queue item
       
        try:
            # Mark as processing
            sync_item.status = 'PROCESSING'
            sync_item.save(update_fields=['status'])
            
            # Route to appropriate handler
            if sync_item.sync_type == 'ORDER_CREATE':
                success = self._sync_order_create(sync_item)
            elif sync_item.sync_type == 'ORDER_UPDATE':
                success = self._sync_order_update(sync_item)
            else:
                logger.warning(f'Unknown sync type: {sync_item.sync_type}')
                success = False
            
            if success:
                sync_item.status = 'COMPLETED'
                sync_item.save()
                
                ActivityLog.objects.create(
                    restaurant_id=sync_item.restaurant_id,
                    level='INFO',
                    module='SYNC_MANAGER',
                    action='SYNC_COMPLETED',
                    details={
                        'sync_id': str(sync_item.id),
                        'sync_type': sync_item.sync_type,
                    }
                )
            else:
                self._handle_sync_failure(sync_item, 'Sync operation failed')
            
            return success
            
        except Exception as e:
            logger.error(
                f'Sync processing error: {str(e)}',
                extra={'sync_id': str(sync_item.id)},
                exc_info=True
            )
            self._handle_sync_failure(sync_item, str(e))
            return False
    
    def _sync_order_create(self, sync_item: SyncQueue) -> bool:
        #Sync new order to Supabase
        
        try:
            payload = sync_item.payload
            order_id = payload.get('local_order_id')
            
            # Get local order
            order = OfflineOrder.objects.get(id=order_id)
            
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
            }
            
            # Sync to Supabase
            supabase_id = self.supabase.sync_order(supabase_data)
            
            if supabase_id:
                # Update local order with Supabase ID
                order.supabase_order_id = supabase_id
                order.sync_status = 'SYNCED'
                order.save(update_fields=['supabase_order_id', 'sync_status'])
                
                sync_item.supabase_id = supabase_id
                return True
            
            return False
            
        except OfflineOrder.DoesNotExist:
            logger.error(f'Order not found: {order_id}')
            sync_item.status = 'CANCELLED'
            sync_item.save()
            return False
        except Exception as e:
            logger.error(f'Order create sync failed: {str(e)}', exc_info=True)
            return False
    
    def _sync_order_update(self, sync_item: SyncQueue) -> bool:
      # Sync order updates to Supabase
       
        try:
            payload = sync_item.payload
            order_id = payload.get('local_order_id')
            supabase_order_id = payload.get('supabase_order_id')
            updates = payload.get('updates', {})
            
            if not supabase_order_id:
                logger.warning('No Supabase order ID for update')
                return False
            
            # Update in Supabase
            success = self.supabase.update_order(supabase_order_id, updates)
            
            if success:
                # Update local status
                order = OfflineOrder.objects.get(id=order_id)
                order.sync_status = 'SYNCED'
                order.save(update_fields=['sync_status'])
            
            return success
            
        except Exception as e:
            logger.error(f'Order update sync failed: {str(e)}', exc_info=True)
            return False
    
    def _handle_sync_failure(self, sync_item: SyncQueue, error_msg: str):
        #Handle sync failure with retry logic
       
        sync_item.mark_retry(error_msg)
        
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
            }
        )
    
    def resolve_conflict(self, sync_item: SyncQueue) -> bool:
        #Resolve sync conflict using last-write-wins strategy
        
        try:
            # Get conflict data
            conflict_data = sync_item.conflict_data
            local_version = conflict_data.get('local_version')
            remote_version = conflict_data.get('remote_version')
            
            # Compare timestamps (last-write-wins)
            if local_version['updated_at'] > remote_version['updated_at']:
                # Local wins - force push
                success = self._force_push_to_supabase(sync_item)
            else:
                # Remote wins - pull and merge
                success = self._pull_from_supabase(sync_item)
            
            if success:
                sync_item.status = 'COMPLETED'
                sync_item.conflict_data = None
                sync_item.save()
            
            return success
            
        except Exception as e:
            logger.error(f'Conflict resolution failed: {str(e)}', exc_info=True)
            return False
    
    def _force_push_to_supabase(self, sync_item: SyncQueue) -> bool:
        #Force push local version to Supabase
        # Implementation similar to regular sync but with force flag
        return self.process_sync_item(sync_item)
    
    def _pull_from_supabase(self, sync_item: SyncQueue) -> bool:
        #Pull remote version and update local\
        try:
            order_id = sync_item.payload.get('local_order_id')
            order = OfflineOrder.objects.get(id=order_id)
            
            # Fetch latest from Supabase
            remote_order = self.supabase.get_order(order.supabase_order_id)
            
            if remote_order:
                # Update local with remote data
                order.order_status = remote_order.get('status', order.order_status)
                order.sync_status = 'SYNCED'
                order.sync_version += 1
                order.save()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f'Pull from Supabase failed: {str(e)}', exc_info=True)
            return False