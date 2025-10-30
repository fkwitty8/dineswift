#CUSTOM EXCEPTION HANDLER


import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger('dineswift')

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_data = {
            'error': response.data,
            'status_code': response.status_code,
        }
        
        # Add correlation ID if available
        request = context.get('request')
        if request and hasattr(request, 'correlation_id'):
            custom_data['correlation_id'] = request.correlation_id
        
        response.data = custom_data
    else:
        # Unhandled exception
        logger.error(f'Unhandled exception: {str(exc)}', exc_info=True)
        response = Response(
            {
                'error': 'Internal server error',
                'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return response