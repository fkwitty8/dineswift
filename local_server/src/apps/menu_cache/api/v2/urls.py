"""
V2 URL Configuration - Flutter App Routes
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'caches', views.ModernMenuCacheViewSet, basename='modern-menu-cache')

urlpatterns = [
    path('', include(router.urls)),
    path('current/', views.get_current_menu, name='flutter-current-menu'),
    path('sync/', views.sync_menu, name='flutter-sync-menu'),
    # Enhanced endpoints for Flutter
    path('preview/', views.get_current_menu, name='menu-preview'),
    path('summary/', views.ModernMenuCacheViewSet.as_view({'get': 'list'}), name='menu-summary'),
]