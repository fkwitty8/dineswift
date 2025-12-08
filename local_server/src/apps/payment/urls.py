from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter

# Create a router for API viewsets (optional for future expansion)
router = DefaultRouter()

urlpatterns = [
    
    # =========================================================================
    # INVOICE ENDPOINTS
    # =========================================================================
    
    path('invoices/', 
         views.InvoiceViewSet.as_view({'post': 'create', 'get': 'list'}), 
         name='invoice-list'),
    path('invoices/<uuid:pk>/', 
         views.InvoiceViewSet.as_view({'get': 'retrieve', 'put': 'update'}), 
         name='invoice-detail'),
    path('invoices/<uuid:invoice_id>/status/', 
         views.get_invoice_status, 
         name='invoice-status'),
    path('invoices/order/<uuid:order_id>/', 
         views.get_order_invoice, 
         name='order-invoice'),
    path('invoices/<uuid:invoice_id>/payments/', 
         views.get_invoice_payments, 
         name='invoice-payments'),
    path('invoices/<uuid:pk>/allocations/', 
     views.InvoiceViewSet.as_view({'get': 'allocations'}), 
     name='invoice-allocations'), 
    
    # =========================================================================
    # PAYMENT ENDPOINTS
    # =========================================================================
    
    path('payments/', 
         views.PaymentViewSet.as_view({'post': 'create', 'get': 'list'}), 
         name='payment-list'),
    path('payments/<uuid:pk>/', 
         views.PaymentViewSet.as_view({'get': 'retrieve'}), 
         name='payment-detail'),
    path('payments/<uuid:payment_id>/allocate/', 
         views.allocate_payment, 
         name='allocate-payment'),
    path('payments/<uuid:payment_id>/complete-cash/', 
         views.complete_cash_payment, 
         name='complete-cash-payment'),
    path('payments/<uuid:payment_id>/refund/', 
         views.request_refund, 
         name='request-refund'),
    path('payments/order/<uuid:order_id>/', 
         views.get_order_payments, 
         name='order-payments'),
    
    # =========================================================================
    # WALLET ENDPOINTS
    # =========================================================================
    
    path('wallet/balance/', 
         views.get_wallet_balance, 
         name='wallet-balance'),
    path('wallet/transactions/', 
         views.get_wallet_transactions, 
         name='wallet-transactions'),
    path('wallet/add-funds/', 
         views.add_wallet_funds, 
         name='add-wallet-funds'),
    # path('wallet/authorize-order/', 
    #      views.authorize_order_payment, 
    #      name='authorize-order-payment'),
    # path('wallet/capture-order/', 
    #      views.capture_order_payment, 
    #      name='capture-order-payment'),
    # path('wallet/release-authorization/', 
    #      views.release_order_authorization, 
    #      name='release-authorization'),
    # path('wallet/payment-methods/', 
    #      views.get_payment_methods, 
    #      name='payment-methods'),
    
    # =========================================================================
    # WEBHOOK ENDPOINTS (No authentication)
    # =========================================================================
    
    path('webhooks/payments/momo/', 
         views.momo_webhook, 
         name='momo-webhook'),
    path('webhooks/payments/card/', 
         views.card_webhook, 
         name='card-webhook'),
    path('webhooks/payments/generic/', 
         views.generic_payment_webhook, 
         name='generic-payment-webhook'),
    # path('webhooks/payments/wallet/', 
    #      views.wallet_webhook, 
    #      name='wallet-webhook'),
    
     # =========================================================================
    # ADMIN/STAFF ENDPOINTS
    # =========================================================================
    
    # path('admin/payments/<uuid:payment_id>/force-complete/', 
    #      views.force_complete_payment, 
    #      name='force-complete-payment'),
    # path('admin/invoices/<uuid:invoice_id>/reconcile/', 
    #      views.reconcile_invoice, 
    #      name='reconcile-invoice'),
    
    # =========================================================================
    # ANALYTICS & REPORTS
    # =========================================================================
    
    # path('reports/payments/summary/', 
    #      views.get_payments_summary, 
    #      name='payments-summary'),
    # path('reports/invoices/summary/', 
    #      views.get_invoices_summary, 
    #      name='invoices-summary'),
    
    ]

# Include router URLs if using viewsets
urlpatterns += router.urls
