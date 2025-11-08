import pytest
from django.core.exceptions import ValidationError
from cloud_api.models import User, Role, UserRole, Restaurant


@pytest.mark.django_db
class TestUserManagement:
    
    @pytest.fixture
    def setup_data(self):
        restaurant = Restaurant.objects.create(
            name='Test Restaurant',
            address={'street': '123 Test St'},
            contact_info={'phone': '+1234567890'},
            operation_hours={'open': '09:00', 'close': '22:00'}
        )
        
        role = Role.objects.create(
            role_name='manager',
            permissions={'can_manage_orders': True}
        )
        
        return {'restaurant': restaurant, 'role': role}
    
    def test_create_user(self):
        """Test user creation"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            phone_number='+1234567890'
        )
        
        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
        assert user.is_active is True
    
    def test_assign_user_role(self, setup_data):
        """Test assigning role to user"""
        user = User.objects.create_user(
            username='manager',
            email='manager@test.com'
        )
        
        user_role = UserRole.objects.create(
            user=user,
            role=setup_data['role'],
            restaurant=setup_data['restaurant']
        )
        
        assert user_role.user == user
        assert user_role.role == setup_data['role']
        assert user_role.is_active is True