from django.urls import path
from . import views

urlpatterns = [
    path('status/', views.get_sync_status, name='sync-status'),
    path('queue/', views.get_sync_queue, name='sync-queue'),
    path('retry-failed/', views.retry_failed_syncs, name='retry-failed'),
    path('force-sync/', views.force_sync, name='force-sync'),
]