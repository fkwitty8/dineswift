from django.urls import path
from . import views

urlpatterns = [
    path('', views.api_home, name='api_home'),
    path('orders/', views.create_order, name='create_order'),
    path('qr/<str:qr_code>/', views.resolve_qr_code, name='resolve_qr_code'),
    path('bookings/', views.create_booking, name='create_booking'),
    path('bookings/<uuid:booking_id>/confirm/', views.confirm_booking_payment, name='confirm_booking'),
    path('payments/', views.process_payment, name='process_payment'),
    path('checkin/<str:ticket_qr>/', views.checkin_booking, name='checkin_booking'),
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/<uuid:supplier_id>/', views.supplier_detail, name='supplier_detail'),
    path('restaurants/<uuid:restaurant_id>/suppliers/', views.restaurant_supplier_list, name='restaurant_supplier_list'),
    path('restaurants/<uuid:restaurant_id>/suppliers/<uuid:relationship_id>/', views.restaurant_supplier_detail, name='restaurant_supplier_detail'),
    path('restaurants/<uuid:restaurant_id>/supply-orders/', views.create_supply_order, name='create_supply_order'),
]
