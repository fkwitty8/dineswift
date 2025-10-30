#PYTEST CONFIGURATION


import pytest
from django.conf import settings
from rest_framework.test import APIClient
from apps.core.models import Restaurant

@pytest.fixture(scope='session')
def django_db_setup():
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'test_dineswift_local',
        'USER': 'postgres',
        'PASSWORD': 'root',
        'HOST': 'localhost',
        'PORT': '5432',
    }

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def test_restaurant(db):
    return Restaurant.objects.create(
        supabase_restaurant_id='00000000-0000-0000-0000-000000000001',
        name='Test Restaurant',
        address={'street': '123 Test St'},
        contact_info={'phone': '555-0100'},
        is_active=True
    )

@pytest.fixture
def authenticated_client(api_client, test_restaurant):
    # Mock JWT token
    token = 'test.jwt.token'
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client