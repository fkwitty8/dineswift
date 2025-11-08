import pytest
from cloud_api.models import Restaurant, RestaurantTable, User, Booking
from datetime import date, time


@pytest.mark.django_db
class TestTableManagement:
    
    @pytest.fixture
    def setup_data(self):
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        
        user = User.objects.create_user(
            username='customer',
            email='customer@test.com'
        )
        
        return {'restaurant': restaurant, 'user': user}
    
    def test_create_table(self, setup_data):
        """Test table creation"""
        table = RestaurantTable.objects.create(
            restaurant=setup_data['restaurant'],
            table_number='T1',
            qr_code='QR123456',
            capacity=4
        )
        
        assert table.table_number == 'T1'
        assert table.capacity == 4
        assert table.table_status == 'available'
    
    def test_table_booking(self, setup_data):
        """Test table booking"""
        table = RestaurantTable.objects.create(
            restaurant=setup_data['restaurant'],
            table_number='T2',
            qr_code='QR789012',
            capacity=6
        )
        
        booking = Booking.objects.create(
            customer_user=setup_data['user'],
            restaurant=setup_data['restaurant'],
            table=table,
            booking_date=date.today(),
            start_time=time(19, 0),
            end_time=time(21, 0),
            party_size=4
        )
        
        assert booking.party_size == 4
        assert booking.status == 'pending'