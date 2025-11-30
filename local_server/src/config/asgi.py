import os
# Importing Django setup utilities first
from django.core.asgi import get_asgi_application 

# Importing Channels components
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Importing Routing definitions from different apps
from apps.payment.routing import websocket_urlpatterns as payment_websocket_urlpatterns
from apps.order_processing.routing import websocket_urlpatterns as order_websocket_urlpatterns

# Set up environment settings
# get_asgi_application() handles the full Django setup internally, 
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Combine all WebSocket URL patterns into a single list
websocket_urlpatterns = (
    payment_websocket_urlpatterns + 
    order_websocket_urlpatterns
)

# Define the main application router
application = ProtocolTypeRouter({
    # 1. HTTP is handled by the standard Django ASGI application
    'http': get_asgi_application(),
    
    # 2. WebSocket handling
    'websocket': AllowedHostsOriginValidator(
        # AuthMiddlewareStack attaches the request user to the connection scope
        AuthMiddlewareStack(
            # URLRouter maps the path to the correct Consumer
            URLRouter(
                websocket_urlpatterns
            )
        )
    ),
})