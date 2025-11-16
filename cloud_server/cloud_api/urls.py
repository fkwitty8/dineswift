from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet
from .booking_views import BookingViewSet
from .account_views import CustomerAccountViewSet
from .qr_views import resolve_qr_code
from .menu_views import get_menu, add_menu_item
from .restaurant_views import restaurant_menu, restaurant_table_info
from .payment_views import validate_payment, verify_transaction
from .ticket_views import generate_ticket, checkin_ticket, ticket_status

router = DefaultRouter()
router.register(r'orders', OrderViewSet)
router.register(r'bookings', BookingViewSet)
router.register(r'accounts', CustomerAccountViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/qr/resolve/', resolve_qr_code, name='resolve_qr_code'),
    path('api/menu/<uuid:menu_id>/', get_menu, name='get_menu'),
    path('api/menu/items/add/', add_menu_item, name='add_menu_item'),
    path('api/restaurant/<uuid:restaurant_id>/menu/', restaurant_menu, name='restaurant_menu'),
    path('restaurant/<uuid:restaurant_id>/table/<uuid:table_id>/', restaurant_table_info, name='restaurant_table'),
    path('api/payment/validate/', validate_payment, name='validate_payment'),
    path('api/payment/verify/', verify_transaction, name='verify_transaction'),
    path('api/tickets/generate/', generate_ticket, name='generate_ticket'),
    path('api/tickets/checkin/<str:qr_code>/', checkin_ticket, name='checkin_ticket'),
    path('api/tickets/status/<str:qr_code>/', ticket_status, name='ticket_status'),
]