from django.urls import path
from . import views

urlpatterns = [
    # Basic sync endpoints
    path('status/', views.get_sync_status, name='sync-status'),
    path('queue/', views.get_sync_queue, name='sync-queue'),
    path('retry-failed/', views.retry_failed_syncs_view, name='retry-failed'),
    path('force-sync/', views.force_sync, name='force-sync'),
    
    # Metrics and detailed information
    path('metrics/', views.get_sync_metrics, name='sync-metrics'),
    
    # Sync item management
    path('cancel/<uuid:sync_id>/', views.cancel_sync_item, name='cancel-sync-item'),
    
    # Admin endpoints
    path('admin/overview/', views.admin_sync_overview, name='admin-sync-overview'),
]