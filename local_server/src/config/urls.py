# src/config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from prometheus_client import make_wsgi_app
from django.http import JsonResponse

def health_check(request):
    from apps.core.models import HealthCheck
    
    checks = HealthCheck.objects.all().values('component', 'is_healthy', 'last_check')
    all_healthy = all(check['is_healthy'] for check in checks)
    
    return JsonResponse({
        'status': 'healthy' if all_healthy else 'degraded',
        'components': list(checks)
    }, status=200 if all_healthy else 503)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Health check
    path('api/health/', health_check),
    
    # Prometheus metrics
    path('metrics/', make_wsgi_app()),
    
    
    # API endpoints - NOW ALL DEFINED!
    path('api/menu-cache/', include('apps.menu_cache.urls')),
    path('api/orders/', include('apps.order_processing.urls')),
    path('api/otp/', include('apps.otp_service.urls')),
    path('api/payments/', include('apps.payment.urls')),
    path('api/sync/', include('apps.sync_manager.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)