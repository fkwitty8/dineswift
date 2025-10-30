#RATE LIMITING

from rest_framework.throttling import UserRateThrottle

class MenuRequestThrottle(UserRateThrottle):
    scope = 'menu_requests'
    
    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.restaurant_id
        else:
            ident = self.get_ident(request)
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

class OrderSubmissionThrottle(UserRateThrottle):
    scope = 'order_submissions'
    
    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.restaurant_id
        else:
            ident = self.get_ident(request)
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

class SyncOperationThrottle(UserRateThrottle):
    scope = 'sync_operations'