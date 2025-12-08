import uuid
from decimal import Decimal
from unittest import TestCase, mock
from rest_framework import serializers
from apps.order_processing.serializer import (
    OrderCreateSerializer, OrderSerializer, OrderStatusUpdateSerializer,
    OrderItemSerializer, OrderWithPaymentSerializer
)

class TestOrderCreateSerializerValidation(TestCase):
    """Tests the custom validation logic in OrderCreateSerializer."""

    def _create_item_data(self, price, quantity, total_key='total_price', total_value=None):
        """Helper to create a single item dictionary."""
        item_data = {
            "id": str(uuid.uuid4()),
            "name": "Test Item",
            "price": str(price),
            "quantity": quantity,
            "special_instructions": ""
        }
        # Include total field if needed for test
        if total_key and total_value is not None:
             item_data[total_key] = str(total_value)
        return item_data

    def test_valid_order_creation_with_matching_totals(self):
        """Test successful validation when the provided total_amount matches the sum of item totals."""
        
        # Item 1: 10.99 * 2 = 21.98
        item1 = self._create_item_data(price=Decimal('10.99'), quantity=2, total_value=Decimal('21.98'))
        
        # Item 2: 13.99 * 4 = 55.96
        item2 = self._create_item_data(price=Decimal('13.99'), quantity=4, total_value=Decimal('55.96'))
        
        # Expected Total Amount (Subtotal) = 21.98 + 55.96 = 77.94
        expected_total_amount = Decimal('77.94')

        data = {
            "items": [item1, item2],
            "total_amount": expected_total_amount,
            "tax_amount": Decimal('0.00'), # Must be present but ignored in comparison
            "customer_phone": "1234567890",
            "payment_method": "cash",
        }

        serializer = OrderCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Serializer failed validation unexpectedly: {serializer.errors}")
        self.assertEqual(serializer.validated_data['total_amount'], expected_total_amount)
        self.assertEqual(serializer.validated_data['calculated_subtotal'], expected_total_amount)

    def test_invalid_order_creation_with_mismatch_totals(self):
        """Test failure when the provided total_amount does NOT match the sum of item totals."""
        
        # Item 1: 10.00 * 2 = 20.00
        item1 = self._create_item_data(price=Decimal('10.00'), quantity=2, total_value=Decimal('20.00'))
        
        # Calculated Subtotal = 20.00
        calculated_subtotal = Decimal('20.00')
        
        # Provided Total is WRONG
        provided_total_amount = Decimal('20.01') 

        data = {
            "items": [item1],
            "total_amount": provided_total_amount,
            "tax_amount": Decimal('0.00'),
            "customer_phone": "1234567890",
            "payment_method": "cash",
        }

        serializer = OrderCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('total_amount', serializer.errors)
        self.assertIn('does not match the calculated amount', serializer.errors['total_amount'][0])

    def test_momo_payment_missing_phone_failure(self):
        """Test failure when payment method is 'momo' but customer_phone is missing."""
        
        # Item 1: 10.00 * 1 = 10.00
        item1 = self._create_item_data(price=Decimal('10.00'), quantity=1, total_value=Decimal('10.00'))
        
        data = {
            "items": [item1],
            "total_amount": Decimal('10.00'),
            "tax_amount": Decimal('0.00'),
            "payment_method": "momo",
            # customer_phone is intentionally omitted/blank by default
        }
        
        serializer = OrderCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('customer_phone', serializer.errors)
        self.assertIn('Phone number is required for Momo payments', serializer.errors['customer_phone'][0])

    def test_momo_payment_with_phone_success(self):
        """Test successful validation when payment method is 'momo' and phone is present."""
        
        # Item 1: 5.00 * 1 = 5.00
        item1 = self._create_item_data(price=Decimal('5.00'), quantity=1, total_value=Decimal('5.00'))
        
        data = {
            "items": [item1],
            "total_amount": Decimal('5.00'),
            "tax_amount": Decimal('0.00'),
            "payment_method": "momo",
            "customer_phone": "9876543210" # Present
        }

        serializer = OrderCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Serializer failed validation unexpectedly: {serializer.errors}")
        self.assertEqual(serializer.validated_data['total_amount'], Decimal('5.00'))

    def test_nested_item_total_mismatch_failure(self):
        """Test failure when the item's total field does not match price * quantity."""
        
        # Item 1: Price=10.00, Quantity=2, but provided total is 19.99 (WRONG)
        item1 = self._create_item_data(price=Decimal('10.00'), quantity=2, total_value=Decimal('19.99'))
        
        data = {
            "items": [item1],
            "total_amount": Decimal('20.00'), # This total amount is correct, but the item total is wrong
            "tax_amount": Decimal('0.00'),
            "payment_method": "cash",
        }

        serializer = OrderCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # The error should be caught by the nested serializer
        self.assertIn('items', serializer.errors)
        # Check that the error is specifically about the item total mismatch
        self.assertIn('Item total (19.99) does not match calculated total_item_price (20.00)', str(serializer.errors))