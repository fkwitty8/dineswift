from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'menus', views.MenuCacheViewSet, basename='menu-cache') 

urlpatterns = [
    path('', include(router.urls)),
    path('sync/', views.sync_menu, name='sync-menu'),
    path('current/', views.get_current_menu, name='current-menu'),
    path('version/', views.get_menu_version, name='menu-version'),
]

"""
Root URL Configuration - Distributor for versioned APIs
"""
from django.urls import path, include

urlpatterns = [
    # Versioned APIs
    path('v1/', include('apps.menu_cache.api.v1.urls')),
    path('v2/', include('apps.menu_cache.api.v2.urls')),
    
    # Default to v2 for new requests
    path('', include('apps.menu_cache.api.v2.urls')),
    
    # Backward compatibility redirects
    path('sync/', include('apps.menu_cache.api.v1.urls')),  # Legacy sync
]
