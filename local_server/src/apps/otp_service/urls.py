from django.urls import path
from . import views

urlpatterns = [
    path('generate/', views.generate_otp, name='generate-otp'),
    path('verify/', views.verify_otp, name='verify-otp'),
    path('order/<uuid:order_id>/', views.get_order_otp, name='order-otp'),
]