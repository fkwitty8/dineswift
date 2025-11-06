from django.urls import path
from . import views

urlpatterns = [
    path('initiate/', views.initiate_payment, name='initiate-payment'),
    path('status/<uuid:payment_id>/', views.get_payment_status, name='payment-status'),
    path('order/<uuid:order_id>/', views.get_order_payment, name='order-payment'),
    path('webhook/momo/', views.momo_webhook, name='momo-webhook'),
]