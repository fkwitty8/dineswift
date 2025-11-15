#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_server.settings')

# Setup Django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Superuser credentials
username = 'admin'
email = 'admin@dineswift.com'
password = 'admin123'

try:
    if User.objects.filter(username=username).exists():
        print(f'User with username "{username}" already exists.')
    else:
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print(f'Superuser "{username}" created successfully!')
        print(f'Username: {username}')
        print(f'Email: {email}')
        print(f'Password: {password}')
except Exception as e:
    print(f'Error creating superuser: {e}')