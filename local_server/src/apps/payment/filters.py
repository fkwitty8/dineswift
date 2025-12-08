import django_filters
from .models import Invoice # Adjust import path as necessary

class InvoiceFilter(django_filters.FilterSet):
    # This filter handles the ?status=PAID parameter
    status = django_filters.CharFilter(field_name='status', lookup_expr='exact') 
    
    # This filter handles the ?start_date/end_date parameters
    start_date = django_filters.DateTimeFilter(field_name='issue_date', lookup_expr='gte')
    end_date = django_filters.DateTimeFilter(field_name='issue_date', lookup_expr='lte')
    
    class Meta:
        model = Invoice
        fields = ['status']