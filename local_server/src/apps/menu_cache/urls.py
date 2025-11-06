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