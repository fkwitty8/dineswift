"""
Supabase Client Service
Handles all interactions with Supabase
"""
import os
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger('dineswift')

# Try to import supabase, but don't fail if not available
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase package not installed. Supabase features will be disabled.")

from django.conf import settings


class SupabaseClient:
    """Singleton Supabase client"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseClient, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Supabase clients with different permission levels"""
        self.client = None
        self.service_client = None
        
        if not SUPABASE_AVAILABLE:
            logger.warning("Supabase not available - running in offline mode")
            return
        
        try:
            supabase_url = settings.SUPABASE_CONFIG.get('url')
            anon_key = settings.SUPABASE_CONFIG.get('anon_key')
            service_key = settings.SUPABASE_CONFIG.get('service_key')
            
            if not supabase_url or not anon_key:
                logger.warning("Supabase credentials not configured - running in offline mode")
                return
            
            # Client for local server operations (uses RLS)
            self.client: Client = create_client(supabase_url, anon_key)
            
            # Service client for administrative operations
            if service_key:
                self.service_client: Client = create_client(supabase_url, service_key)
            
            logger.info("Supabase clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Supabase clients: {str(e)}")
            self.client = None
            self.service_client = None
    
    def is_available(self) -> bool:
        """Check if Supabase is available and configured"""
        return self.client is not None
    
    def set_restaurant_context(self, restaurant_id: str):
        """Set restaurant context for RLS policies"""
        if not self.is_available():
            return
        
        try:
            # This header will be used by Supabase RLS policies
            self.client.postgrest.session.headers.update({
                'x-restaurant-id': restaurant_id
            })
        except Exception as e:
            logger.error(f"Failed to set restaurant context: {str(e)}")
    
    # ========================================================================
    # MENU OPERATIONS
    # ========================================================================
    
    def get_menu(self, restaurant_id: str) -> Optional[Dict]:
        """Get menu data from Supabase"""
        if not self.is_available():
            logger.warning("Supabase not available - cannot fetch menu")
            return None
        
        try:
            response = self.client.table('menus')\
                .select('*')\
                .eq('restaurant_id', restaurant_id)\
                .eq('is_active', True)\
                .execute()
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            logger.error(f"Failed to fetch menu: {str(e)}")
            return None
    
    # ========================================================================
    # ORDER OPERATIONS
    # ========================================================================
    
    def sync_order(self, order_data: Dict) -> Optional[str]:
        """Sync order to Supabase with conflict resolution"""
        if not self.is_available():
            logger.warning("Supabase not available - order queued for later sync")
            return None
        
        try:
            response = self.client.table('orders')\
                .upsert(order_data, on_conflict='local_order_id')\
                .execute()
            
            if response.data:
                return response.data[0]['id']
            return None
            
        except Exception as e:
            logger.error(f"Failed to sync order: {str(e)}")
            return None
    
    def update_order(self, supabase_order_id: str, updates: Dict) -> bool:
        """Update order in Supabase"""
        if not self.is_available():
            logger.warning("Supabase not available - update queued for later sync")
            return False
        
        try:
            response = self.client.table('orders')\
                .update(updates)\
                .eq('id', supabase_order_id)\
                .execute()
            
            return len(response.data) > 0
            
        except Exception as e:
            logger.error(f"Failed to update order: {str(e)}")
            return False
    
    def get_order(self, supabase_order_id: str) -> Optional[Dict]:
        """Get order from Supabase"""
        if not self.is_available():
            return None
        
        try:
            response = self.client.table('orders')\
                .select('*')\
                .eq('id', supabase_order_id)\
                .execute()
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            logger.error(f"Failed to get order: {str(e)}")
            return None
    
    def batch_sync_orders(self, orders: List[Dict]) -> List[Dict]:
        """Batch sync multiple orders"""
        if not self.is_available():
            logger.warning("Supabase not available - orders queued for later sync")
            return []
        
        try:
            response = self.client.table('orders')\
                .upsert(orders, on_conflict='local_order_id')\
                .execute()
            
            return response.data
            
        except Exception as e:
            logger.error(f"Failed to batch sync orders: {str(e)}")
            return []
    
    # ========================================================================
    # HEALTH CHECK
    # ========================================================================
    
    def health_check(self) -> bool:
        """Check if Supabase is reachable"""
        if not self.is_available():
            return False
        
        try:
            response = self.client.table('restaurants').select('id').limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Supabase health check failed: {str(e)}")
            return False


# Singleton instance
supabase_client = SupabaseClient()