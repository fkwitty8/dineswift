#UPABASE JWT AUTH

import jwt
import logging
from django.conf import settings
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from apps.core.models import Restaurant

logger = logging.getLogger('dineswift')

class SupabaseAuthentication(authentication.BaseAuthentication):
   #Authenticate users via Supabase JWT tokens
    
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('Bearer '):
            return None
        
        token = auth_header.split(' ')[1]
        
        try:
            # Decode JWT token
            payload = jwt.decode(
                token,
                settings.SUPABASE_CONFIG['jwt_secret'],
                algorithms=['HS256'],
                audience='authenticated',
            )
            
            # Extract user info
            user_id = payload.get('sub')
            email = payload.get('email')
            restaurant_id = payload.get('restaurant_id')
            role = payload.get('role', 'staff')
            
            if not user_id or not restaurant_id:
                raise AuthenticationFailed('Invalid token payload')
            
            # Verify restaurant exists in local DB
            try:
                restaurant = Restaurant.objects.get(
                    supabase_restaurant_id=restaurant_id,
                    is_active=True
                )
            except Restaurant.DoesNotExist:
                raise AuthenticationFailed('Restaurant not found or inactive')
            
            # Create user object with claims
            user = SupabaseUser(
                id=user_id,
                email=email,
                restaurant_id=restaurant.id,
                supabase_restaurant_id=restaurant_id,
                role=role,
                token=token
            )
            
            return (user, token)
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            logger.warning(f'Invalid JWT token: {str(e)}')
            raise AuthenticationFailed('Invalid authentication token')
        except Exception as e:
            logger.error(f'Authentication error: {str(e)}', exc_info=True)
            raise AuthenticationFailed('Authentication failed')

class SupabaseUser:
    
   # Mock user object for Supabase authenticated users
  
    
    def __init__(self, id, email, restaurant_id, supabase_restaurant_id, role, token):
        self.id = id
        self.email = email
        self.restaurant_id = restaurant_id
        self.supabase_restaurant_id = supabase_restaurant_id
        self.role = role
        self.token = token
        self.is_authenticated = True
        self.is_active = True
    
    def __str__(self):
        return self.email
    
    def has_perm(self, perm):
        return self.role in ['admin', 'manager']
    
    def has_module_perms(self, app_label):
        return True