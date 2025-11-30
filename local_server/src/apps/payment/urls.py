from django.urls import path
from . import views

urlpatterns = [
    # =========================================================================
    # INVOICE ENDPOINTS
    # =========================================================================
    path('invoices/create/', views.create_invoice, name='create-invoice'),
    path('invoices/<uuid:invoice_id>/status/', views.get_invoice_status, name='invoice-status'),
    path('invoices/order/<uuid:order_id>/', views.get_order_invoice, name='order-invoice'),
    
    # =========================================================================
    # PAYMENT ENDPOINTS
    # =========================================================================
    path('payments/initiate/', views.initiate_payment, name='initiate-payment'),
    path('payments/<uuid:payment_id>/status/', views.get_payment_status, name='payment-status'),
    path('payments/<uuid:payment_id>/allocate/', views.allocate_payment, name='allocate-payment'),
    path('payments/<uuid:payment_id>/refund/', views.request_refund, name='request-refund'),
    path('payments/order/<uuid:order_id>/', views.get_order_payments, name='order-payments'),
    
    # =========================================================================
    # WALLET ENDPOINTS
    # =========================================================================
    path('wallet/balance/', views.get_wallet_balance, name='wallet-balance'),
    path('wallet/transactions/', views.get_wallet_transactions, name='wallet-transactions'),
    path('wallet/add-funds/', views.add_wallet_funds, name='add-wallet-funds'),
    path('wallet/payment-methods/', views.get_payment_methods, name='payment-methods'),
    
    # =========================================================================
    # WEBHOOK ENDPOINTS (No authentication)
    # =========================================================================
    path('webhooks/payments/momo/', views.momo_webhook, name='momo-webhook'),
    path('webhooks/payments/card/', views.card_webhook, name='card-webhook'),
    path('webhooks/payments/generic/', views.generic_payment_webhook, name='generic-payment-webhook'),
]