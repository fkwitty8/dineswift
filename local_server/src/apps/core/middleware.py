#CUSTOM MIDDLEWARE

import time
import uuid
import logging
from django.utils.deprecation import MiddlewareMixin
from prometheus_client import Counter, Histogram

logger = logging.getLogger('dineswift')

# Prometheus metrics
request_count = Counter('dineswift_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('dineswift_request_duration_seconds', 'Request duration', ['method', 'endpoint'])

class LoggingMiddleware(MiddlewareMixin):
    #Add correlation ID and structured logging
    
    def process_request(self, request):
        # Add correlation ID
        request.correlation_id = str(uuid.uuid4())
        request.start_time = time.time()
        
        logger.info(
            'Request started',
            extra={
                'correlation_id': request.correlation_id,
                'method': request.method,
                'path': request.path,
                'ip': self.get_client_ip(request),
            }
        )
    
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            
            logger.info(
                'Request completed',
                extra={
                    'correlation_id': getattr(request, 'correlation_id', 'unknown'),
                    'method': request.method,
                    'path': request.path,
                    'status': response.status_code,
                    'duration_ms': round(duration * 1000, 2),
                }
            )
        
        return response
    
    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class SecurityHeadersMiddleware(MiddlewareMixin):
    #Add security headers
    
    def process_response(self, request, response):  # Add 'request' parameter here
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response

class MetricsMiddleware(MiddlewareMixin):
    #Collect Prometheus metrics
    
    
    def process_request(self, request):
        request._metrics_start_time = time.time()
    
    def process_response(self, request, response):
        if hasattr(request, '_metrics_start_time'):
            duration = time.time() - request._metrics_start_time
            
            endpoint = request.path
            method = request.method
            status = response.status_code
            
            request_count.labels(method=method, endpoint=endpoint, status=status).inc()
            request_duration.labels(method=method, endpoint=endpoint).observe(duration)
        
        return response