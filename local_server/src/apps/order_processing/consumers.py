#WEBSOCKET SUPPORT

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from apps.order_processing.models import OfflineOrder

logger = logging.getLogger('dineswift')

class OrderStatusConsumer(AsyncWebsocketConsumer):
    #WebSocket consumer for real-time order status updates
    
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f'order_{self.order_id}'
        
        # Verify user has access to this order
        has_access = await self.verify_order_access()
        
        if not has_access:
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send current order status
        order_data = await self.get_order_data()
        await self.send(text_data=json.dumps({
            'type': 'order_status',
            'data': order_data
        }))
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        # Handle incoming messages (e.g., ping)
        data = json.loads(text_data)
        
        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({
                'type': 'ping'
            }))
    
    async def order_update(self, event):
       # Receive order update from channel layer
        
        await self.send(text_data=json.dumps({
            'type': 'order_status',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def verify_order_access(self):
        #Verify user has access to this order
        try:
            user = self.scope.get('user')
            if not user or not user.is_authenticated:
                return False
            
            order = OfflineOrder.objects.get(id=self.order_id)
            return str(order.restaurant_id) == str(user.restaurant_id)
            
        except OfflineOrder.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_order_data(self):
        #Get current order data
        try:
            order = OfflineOrder.objects.get(id=self.order_id)
            return {
                'id': str(order.id),
                'local_order_id': order.local_order_id,
                'status': order.order_status,
                'total_amount': float(order.total_amount),
                'estimated_prep_time': order.estimated_preparation_time,
                'created_at': order.created_at.isoformat(),
            }
        except OfflineOrder.DoesNotExist:
            return None