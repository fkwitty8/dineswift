
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r'ws/staff/notifications/(?P<restaurant_id>[^/]+)/$',
        consumers.StaffNotificationsConsumer.as_asgi()
    ),
]