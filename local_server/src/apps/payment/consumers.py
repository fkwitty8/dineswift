
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import logging

logger = logging.getLogger('dineswift.websocket')

class StaffNotificationsConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for staff notifications using Django Channels
    """
    
    async def connect(self):
        """Staff user connects to their restaurant's notification channel"""
        try:
            # Extract restaurant ID from URL route or query string
            self.restaurant_id = self.scope['url_route']['kwargs']['restaurant_id']
            self.room_group_name = f'restaurant_{self.restaurant_id}_staff'
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            await self.accept()
            
            # Send connection confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': f'Connected to restaurant {self.restaurant_id} notifications',
                'room': self.room_group_name,
                'timestamp': self._get_current_timestamp()
            }))
            
            logger.info(f"WebSocket connected: {self.room_group_name}")
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {str(e)}")
            await self.close()
    
    async def disconnect(self, close_code):
        """Leave room group on disconnect"""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected: {self.room_group_name}")
    
    async def receive(self, text_data):
        """Receive message from WebSocket (client to server)"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'payment_collected':
                await self.handle_payment_collected(text_data_json)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat()
            elif message_type == 'subscribe':
                await self.handle_subscription(text_data_json)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received in WebSocket")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")
    
    async def staff_notification(self, event):
        """
        Receive notification from room group and send to WebSocket.
        This method name matches the 'type' in group_send.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'event': event['event'],
                'data': event['data'],
                'timestamp': event.get('timestamp'),
                'server_id': event.get('server_id')
            }))
        except Exception as e:
            logger.error(f"Error sending notification to WebSocket: {str(e)}")
    
    async def handle_payment_collected(self, data):
        """Handle payment collection confirmation from staff"""
        try:
            payment_id = data.get('payment_id')
            staff_user_id = data.get('staff_user_id')
            
            # Process the payment collection
            from apps.payment.services import payment_service
            result = await database_sync_to_async(
                payment_service.complete_cash_payment
            )(payment_id, staff_user_id)
            
            # Send result back to client
            await self.send(text_data=json.dumps({
                'type': 'payment_collection_result',
                'success': result.get('success', False),
                'payment_id': payment_id,
                'message': result.get('message', 'Unknown error'),
                'timestamp': self._get_current_timestamp()
            }))
            
        except Exception as e:
            logger.error(f"Payment collection handling failed: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'payment_collection_result',
                'success': False,
                'error': str(e),
                'timestamp': self._get_current_timestamp()
            }))
    
    async def handle_heartbeat(self):
        """Handle heartbeat to keep connection alive"""
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_ack',
            'timestamp': self._get_current_timestamp()
        }))
    
    async def handle_subscription(self, data):
        """Handle client subscription to specific event types"""
        event_types = data.get('events', [])
        # Could implement filtering logic here
        await self.send(text_data=json.dumps({
            'type': 'subscription_confirmed',
            'events': event_types,
            'timestamp': self._get_current_timestamp()
        }))
    
    def _get_current_timestamp(self):
        """Get current timestamp in ISO format"""
        from django.utils import timezone
        return timezone.now().isoformat()