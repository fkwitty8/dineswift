from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import Order

@api_view(['GET'])
def order_count(request):
    """
    Returns the total number of orders in the system
    """
    count = Order.objects.count()
    return Response({'order_count': count})