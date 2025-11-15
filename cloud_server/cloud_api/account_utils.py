from .models import CustomerAccount

def get_or_create_customer_account(user_id, restaurant_id, account_type='wallet'):
    """Get or create customer account for a restaurant"""
    account, created = CustomerAccount.objects.get_or_create(
        user_id=user_id,
        restaurant_id=restaurant_id,
        account_type=account_type,
        defaults={
            'balance': 0.00,
            'is_refundable': True
        }
    )
    return account, created

def check_sufficient_balance(account, amount):
    """Check if account has sufficient balance for transaction"""
    return account.balance >= amount