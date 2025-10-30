"""
Main URL Configuration for Local Server
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

# Health check endpoint
@require_http_methods(["GET"])
def health_check(request):
    """Simple health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'service': 'dineswift-local-server',
        'version': '1.0.0'
    })

# Root API endpoint
@require_http_methods(["GET"])
def api_root(request):
    """API root endpoint"""
    return JsonResponse({
        'name': 'DineSwift Local Server',
        'version': '1.0.0',
        'description': 'Food ordering and restaurant management system - Local Development',
        'endpoints': {
            'admin': '/admin/',
            'health': '/health/',
            'api_docs': 'Coming soon...',
        },
        'status': 'running'
    })

urlpatterns = [
    # Root endpoint
    path('', api_root, name='api-root'),
    
    # Admin interface
    path('admin/', admin.site.urls),
    
    # Health check
    path('health/', health_check, name='health_check'),
    
    # API endpoints (will create these next)
    # path('api/orders/', include('apps.order_processing.urls')),
    # path('api/menu/', include('apps.menu_cache.urls')),
    # path('api/otp/', include('apps.otp_service.urls')),
    # path('api/sync/', include('apps.sync_manager.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)