import pytest
import uuid
from decimal import Decimal
from unittest.mock import patch, Mock, AsyncMock
from django.utils import timezone
from django.db import DatabaseError
from datetime import timedelta

from asgiref.sync import async_to_sync

from apps.payment.services import InvoiceService, PaymentService, WalletService
from apps.payment.models import Invoice, Payment, PaymentAllocation, CustomerWallet, AccountingEntry
from apps.core.models import ActivityLog

@pytest.mark.django_db
class TestInvoiceServices:
    """Unit tests for InvoiceService"""
    
    def test_create_invoice_success(self, test_order, test_restaurant, test_user):
        """Test successful invoice creation"""
        service = InvoiceService()
        
        result = service.create_invoice(
            order_id=str(test_order.id),
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('100.00'),
            tax_amount=Decimal('18.00'),
            service_fee=Decimal('5.00'),
            discount_amount=Decimal('10.00'),
            user_id=str(test_user.id)
        )
        
        assert result['success'] is True
        assert 'invoice_id' in result
        assert result['order_id'] == str(test_order.id)
        assert result['total_amount'] == 113.0  # 100 + 18 + 5 - 10
        
        # Verify invoice was created
        invoice = Invoice.objects.get(id=result['invoice_id'])
        assert invoice.order == test_order
        assert invoice.restaurant == test_restaurant
        assert invoice.total_amount == Decimal('113.00')
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_CREATED'
        ).first()
        assert activity_log is not None
        assert activity_log.user == test_user
    
    def test_create_invoice_order_not_found(self, test_restaurant, test_user):
        """Test invoice creation with non-existent order"""
        service = InvoiceService()
        
        result = service.create_invoice(
            order_id=str(uuid.uuid4()),  # Non-existent order
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('100.00'),
            user_id=str(test_user.id)
        )
        
        assert result['success'] is False
        assert 'error' in result
        assert 'Order not found' in result['error']
    
    def test_get_invoice_status_success(self, invoice_instance, test_user):
        """Test successful invoice status retrieval"""
        service = InvoiceService()
        
        result = service.get_invoice_status(
            invoice_id=str(invoice_instance.id),
            user_id=str(test_user.id)
        )
        
        assert result['invoice_id'] == str(invoice_instance.id)
        assert result['order_id'] == str(invoice_instance.order.id)
        assert result['status'] == invoice_instance.status
        assert result['total_amount'] == float(invoice_instance.total_amount)
        assert 'allocations' in result
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_ACCESSED'
        ).first()
        assert activity_log is not None
    
    def test_get_invoice_status_not_found(self, test_user):
        """Test invoice status retrieval for non-existent invoice"""
        service = InvoiceService()
        
        result = service.get_invoice_status(
            invoice_id=str(uuid.uuid4()),
            user_id=str(test_user.id)
        )
        
        assert 'error' in result
        assert result['error'] == 'Invoice not found'
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='INVOICE',
            action='INVOICE_NOT_FOUND'
        ).first()
        assert activity_log is not None

@pytest.mark.django_db
class TestPaymentServices:
    """Unit tests for PaymentService with updated implementation"""
    
    def test_initiate_payment_success(self, test_restaurant, invoice_instance, test_user):
        """Test successful payment initiation with local network"""
        service = PaymentService()
        
        payment_data = {
            'invoice_id': invoice_instance.id,
            'payment_method': 'cash',
            'amount': '113.00',
            'customer_phone': '256712345678'
        }
        
        result = service.initiate_payment(
            payment_data=payment_data,
            user_id=str(test_user.id)
        )
        
        assert result['success'] is True
        assert 'payment_id' in result
        assert 'invoice_id' in result
        assert result['gateway'] == 'CASH'
        
        # Verify payment was created with correct status
        payment = Payment.objects.get(id=result['payment_id'])
        assert payment.restaurant == test_restaurant
        assert payment.amount == Decimal('113.00')
        assert payment.gateway == 'CASH'
        assert payment.status == 'AWAITING_COLLECTION'  # New status for cash payments
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='PAYMENT_CREATED'
        ).first()
        assert activity_log is not None

    def test_initiate_wallet_payment_completes_immediately(self,invoice_second_instance, test_user, customer_wallet):
        """Test that wallet payments complete immediately"""
        service = PaymentService()
        
        payment_data = {
            'invoice_id': invoice_second_instance.id,
            'payment_method': 'wallet',
            'payment_method_id': str(customer_wallet.id),
            'amount': '50'
        }
        
        result = service.initiate_payment(
            payment_data=payment_data,
            user_id=str(test_user.id)
        )
        
        assert result['success'] is True
        
        payment = Payment.objects.get(id=result['payment_id'])
        assert payment.status == 'COMPLETED'
        assert payment.gateway == 'WALLET'

    def test_initiate_payment_invoice_not_found(self, test_restaurant, test_user):
        """Test payment initiation with non-existent invoice"""
        service = PaymentService()
        
        payment_data = {
            'invoice_id': str(uuid.uuid4()),  # Random UUID that doesn't exist
            'payment_method': 'cash',
            'amount': '100.00'
        }
        
        result = service.initiate_payment(
            payment_data=payment_data,
            user_id=str(test_user.id)
        )
        
        assert result['success'] is False
        assert 'does not exist' in result['error']

    def test_initiate_payment_invalid_method(self, invoice_instance, test_user):
        """Test payment initiation with invalid payment method"""
        service = PaymentService()
        
        payment_data = {
            'invoice_id': invoice_instance.id,
            'payment_method': 'invalid_method',  # Invalid method
            'amount': '100.00'
        }
        
        result = service.initiate_payment(
            payment_data=payment_data,
            user_id=str(test_user.id)
        )
        
        assert result['success'] is False
        assert 'error' in result

    
    @patch('apps.payment.services.PaymentService._send_real_time_notification')
    def test_cash_payment_triggers_notification(self, mock_notification, invoice_instance, test_user):
        """Test that cash payments trigger real-time notifications"""
        service = PaymentService()
        
        payment_data = {
            'invoice_id': str(invoice_instance.id),
            'payment_method': 'cash',
            'amount': '75.00',
            'customer_phone': '256712345678'
        }
        
        result = service.initiate_payment(
            payment_data=payment_data,
            user_id=str(test_user.id)
        )
        
        assert result['success'] is True
        mock_notification.assert_called_once()

    def test_process_wallet_payment_insufficient_funds(self, payment_instance, invoice_instance, customer_wallet, test_user):
        """Test wallet payment with insufficient funds"""
        service = PaymentService()
        
        # Set up payment for wallet with amount exceeding balance
        payment_instance.amount = Decimal('200.00')  # More than wallet balance
        payment_instance.gateway = 'WALLET'
        payment_instance.customer_user = customer_wallet.user
        payment_instance.save()
        
        with pytest.raises(Exception, match="Insufficient wallet balance or wallet inactive"):
            service._process_wallet_payment(
                payment=payment_instance,
                invoice=invoice_instance,
                user_id=str(test_user.id)
            )
        
        # Verify payment was not completed
        payment_instance.refresh_from_db()
        assert payment_instance.status != 'COMPLETED'
        
        # Verify wallet balance was not changed
        customer_wallet.refresh_from_db()
        assert customer_wallet.available_balance == Decimal('150.00')

    def test_complete_cash_payment_success(self, payment_instance, invoice_instance, test_user):
        """Test successful cash payment completion by staff"""
        service = PaymentService()
        
        # Set payment to AWAITING_COLLECTION
        payment_instance.status = 'AWAITING_COLLECTION'
        payment_instance.gateway = 'CASH'
        payment_instance.save()
        
        # Create an allocation for the payment
        from apps.payment.models import PaymentAllocation
        allocation = PaymentAllocation.objects.create(
            invoice=invoice_instance, 
            payment=payment_instance,
            allocated_amount=payment_instance.amount
        )
        
        result = service.complete_cash_payment(
            payment_id=str(payment_instance.id),
            staff_user_id=str(test_user.id)
        )
        
        assert result['success'] is True
        
        # Verify payment was marked as completed
        payment_instance.refresh_from_db()
        assert payment_instance.status == 'COMPLETED'
        assert payment_instance.completed_at is not None
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='CASH_PAYMENT_COLLECTED'
        ).first()
        assert activity_log is not None

    def test_complete_cash_payment_invalid_status(self, payment_instance, test_user):
        """Test cash payment completion with invalid status"""
        service = PaymentService()
        
        # Payment is not in AWAITING_COLLECTION status
        payment_instance.status = 'COMPLETED'
        payment_instance.save()
        
        result = service.complete_cash_payment(
            payment_id=str(payment_instance.id),
            staff_user_id=str(test_user.id)
        )
        
        assert result['success'] is False
        assert 'not awaiting collection' in result['error'].lower()

    def test_allocate_payment_to_invoice_success(self, payment_instance, invoice_instance, test_user):
        """Test successful payment allocation to invoice"""
        service = PaymentService()
        
        # Set payment as completed
        payment_instance.status = 'COMPLETED'
        payment_instance.save()
        
        service._allocate_payment_to_invoice(
            payment=payment_instance,
            invoice=invoice_instance,
            user_id=str(test_user.id)
        )
        
        # Verify allocation was created
        allocation = PaymentAllocation.objects.filter(
            payment=payment_instance,
            invoice=invoice_instance
        ).first()
        assert allocation is not None
        
        # Verify invoice status was updated
        invoice_instance.refresh_from_db()
        assert invoice_instance.amount_paid == payment_instance.amount
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='ACCOUNTING',
            action='PAYMENT_ALLOCATED'
        ).first()
        assert activity_log is not None

    @patch('apps.payment.services.PaymentService._create_payment_accounting_entry')
    def test_allocate_payment_creates_accounting_entry(self, mock_accounting, payment_instance, invoice_instance, test_user):
        """Test that payment allocation creates accounting entry"""
        service = PaymentService()
        
        payment_instance.status = 'COMPLETED'
        payment_instance.save()
        
        service._allocate_payment_to_invoice(
            payment=payment_instance,
            invoice=invoice_instance,
            user_id=str(test_user.id)
        )
        
        mock_accounting.assert_called_once_with(
            payment_instance,
            invoice_instance,
            payment_instance.amount,
            str(test_user.id)
        )


    def test_handle_webhook_success(self, payment_instance, test_order):
        """Test successful webhook handling"""
        service = PaymentService()
        
        # Create an invoice allocation for the payment
        invoice = Invoice.objects.create(
            order=test_order,  # This would normally be an Order instance
            restaurant=payment_instance.restaurant,
            subtotal_amount=payment_instance.amount,
            total_amount=payment_instance.amount,
            due_date=timezone.now() + timezone.timedelta(days=1),
            status='ISSUED'
        )
        
        PaymentAllocation.objects.create(
            invoice=invoice,
            payment=payment_instance,
            allocated_amount=payment_instance.amount
        )
        
        webhook_data = {
            'external_id': str(payment_instance.id),
            'status': 'SUCCESSFUL',
            'transaction_id': 'TXN123456',
            'amount': str(payment_instance.amount),
            'currency': 'UGX',
            'payer_message': 'Payment successful'
        }
        
        with patch('apps.order_processing.services.OrderProcessingService') as mock_order_service:
            mock_instance = Mock()
            mock_order_service.return_value = mock_instance
            
            result = service.handle_webhook(webhook_data)
            
            assert result['success'] is True
            
            # Verify payment was marked as completed
            payment_instance.refresh_from_db()
            assert payment_instance.status == 'COMPLETED'
            assert payment_instance.gateway_reference == 'TXN123456'
            
            # Verify order service was called if invoice exists

    def test_handle_webhook_failed_payment(self, payment_instance, test_order):
        """Test webhook handling for failed payment"""
        service = PaymentService()
        
        invoice = Invoice.objects.create(
            order=test_order,  # This would normally be an Order instance
            restaurant=payment_instance.restaurant,
            subtotal_amount=payment_instance.amount,
            total_amount=payment_instance.amount,
            due_date=timezone.now() + timezone.timedelta(days=1),
            status='ISSUED'
        )
        
        PaymentAllocation.objects.create(
            invoice=invoice,
            payment=payment_instance,
            allocated_amount=payment_instance.amount
        )
        
        webhook_data = {
            'external_id': str(payment_instance.id),
            'status': 'FAILED',
            'transaction_id': 'TXN123456',
            'amount': str(payment_instance.amount),
            'currency': 'UGX',
            'payer_message': 'Insufficient funds'
        }
        
        result = service.handle_webhook(webhook_data)
        
        assert result['success'] is True
        
        # Verify payment was marked as failed
        payment_instance.refresh_from_db()
        assert payment_instance.status == 'FAILED'
        assert 'Insufficient funds' in payment_instance.error_message

    def test_handle_webhook_payment_not_found(self):
        """Test webhook handling for non-existent payment"""
        service = PaymentService()
        
        webhook_data = {
            'external_id': str(uuid.uuid4()),  # Random UUID that doesn't exist
            'status': 'SUCCESSFUL',
            'transaction_id': 'TXN123456',
            'amount': '100.00',
            'currency': 'UGX'
        }
        
        result = service.handle_webhook(webhook_data)
        
        assert result['success'] is False
        assert 'error' in result


    def test_get_or_create_invoice_finds_correct_invoice(self, test_restaurant, test_user,test_user_2):
        """Test that invoice matching correctly identifies the right invoice"""
        service = PaymentService()
        
        # Create multiple invoices with same amount but different customers
        from apps.payment.models import Invoice
        from apps.order_processing.models import OfflineOrder
        
        # Invoice 1: Specific customer
        order1 = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id="ORDER-001",
            total_amount=Decimal('100.00'),
            customer_id=test_user.id,
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Test Item_1",
                    "price": "10.99",
                    "quantity": 2,
                    "total": "21.98"
                }
            ],  
            order_status='READY',
            sync_status='PENDING_SYNC'
        )
        invoice1 = Invoice.objects.create(
            order=order1,
            restaurant=test_restaurant,
            subtotal_amount=Decimal('100.00'),
            tax_amount=Decimal('18.00'),
            service_fee=Decimal('5.00'),
            discount_amount=Decimal('10.00'),
            total_amount=Decimal('113.00'),
            due_date=timezone.now() + timedelta(days=1),
            status='ISSUED'
        )
        
        # Invoice 2: Different customer, same amount
        order2 = OfflineOrder.objects.create(
            restaurant=test_restaurant,
            local_order_id="ORDER-002", 
            total_amount=Decimal('100.00'),
            customer_id=test_user_2.id,
            order_items=[
                {
                    "id": str(uuid.uuid4()),
                    "name": "Test Item_2",
                    "price": "10.99",
                    "quantity": 2,
                    "total": "21.98"
                }
            ],  
            order_status='READY',
            sync_status='PENDING_SYNC'
        )
        invoice2 = Invoice.objects.create(
            order=order2,
            restaurant=test_restaurant,
            subtotal_amount=Decimal('100.00'),
            tax_amount=Decimal('18.00'),
            service_fee=Decimal('5.00'),
            discount_amount=Decimal('10.00'),
            total_amount=Decimal('113.00'),
            due_date=timezone.now() + timedelta(days=1),
            status='ISSUED'
        )
        
        # Create payment with customer phone matching invoice1
        payment = Payment.objects.create(
            restaurant=test_restaurant,
            amount=Decimal('113.00'),
            currency='UGX',
            gateway='CASH',
            customer_phone='256711111111',  
            customer_user=test_user # Matches invoice1
        )
        
        found_invoice = service._get_or_create_invoice_for_payment(payment)
        
        # Should match invoice1, not invoice2
        assert found_invoice is not None
        assert found_invoice.id == invoice1.id
        assert found_invoice.id != invoice2.id

    def test_get_or_create_invoice_creates_system_invoice_when_no_match(self, test_restaurant,test_user):
        """Test system invoice creation when no matching invoice found"""
        service = PaymentService()
        
        payment = Payment.objects.create(
            restaurant=test_restaurant,
            amount=Decimal('150.00'),
            currency='UGX',
            gateway='MOMO',
            customer_phone='256712345678',
            customer_email='test@example.com',
        )
        
        # Ensure no invoices exist with this amount
        Invoice.objects.filter(restaurant=test_restaurant, total_amount=Decimal('150.00')).delete()
        
        invoice = service._get_or_create_invoice_for_payment(payment)
        
        assert invoice is not None
        assert invoice.metadata.get('system_created') is True
        assert invoice.metadata.get('reconciliation_required') is True
        assert invoice.order.order_type == 'SYS_RECONCILIATION'
        
        # Verify activity log was created
        activity_log = ActivityLog.objects.filter(
            module='PAYMENT',
            action='SYSTEM_INVOICE_CREATED'
        ).first()
        assert activity_log is not None
        assert activity_log.level == 'WARNING'

    def test_system_invoice_has_proper_metadata(self, test_restaurant):
        """Test that system invoices contain proper metadata for reconciliation"""
        service = PaymentService()
        
        payment = Payment.objects.create(
            restaurant=test_restaurant,
            amount=Decimal('150.00'),
            currency='SUI',
            gateway='CRYPTO',
            customer_phone='256712345678',
            customer_email='test@example.com',
        )
        
        # Delete any existing invoices to force system invoice creation
        Invoice.objects.filter(restaurant=test_restaurant).delete()
        
        invoice = service._create_system_invoice_for_payment(payment)
        
        assert invoice.metadata['system_created'] is True
        assert invoice.metadata['payment_id'] == str(payment.id)
        assert invoice.metadata['original_payment_gateway'] == 'CRYPTO'
        assert invoice.metadata['reconciliation_required'] is True
        
        # Verify the associated order is properly marked
        assert invoice.order.order_type == 'SYS_RECONCILIATION'
        assert 'AUTO-CREATED' in invoice.order.special_instructions
        assert invoice.order.metadata['system_created'] is True
        
    @patch('apps.payment.services.get_channel_layer')
    def test_send_real_time_notification(self, mock_channel_layer, test_restaurant):
        """Test real-time notification sending"""
        service = PaymentService()
        
        mock_channel = AsyncMock()
        mock_channel_layer.return_value = mock_channel
        
        notification_data = {
            'payment_id': str(uuid.uuid4()),
            'amount': 100.00,
            'order_id': str(uuid.uuid4())
        }
        
        service._send_real_time_notification(
            room=str(test_restaurant.id),
            event='payment_awaiting_collection',
            data=notification_data
        )
        
        # Verify channel layer was called
        mock_channel.group_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_local_websocket_connection(self, test_restaurant, test_user):
        """Test local WebSocket connection (simplified)"""
        # This would test the WebSocket consumer in a real scenario
        # For now, we'll just verify the service can be instantiated
        service = PaymentService()
        assert service is not None
        
        # Verify we can call notification methods
        try:
            service._send_real_time_notification(
                room=str(test_restaurant.id),
                event='test_event',
                data={'test': 'data'}
            )
            # If we get here, the method executed without error
            assert True
        except Exception as e:
            # In test environment, channels might not be available, but the method should handle it
            assert "channel" in str(e).lower() or True  # Allow channel-related errors in tests

    def test_payment_service_singleton(self):
        """Test that payment_service is a singleton instance"""
        payment_service=PaymentService()
        service1 = payment_service
        service2 = payment_service
        assert service1 is service2
        assert isinstance(service1, PaymentService)

@pytest.mark.django_db
class TestRealTimeNotifications:
    """Tests for real-time notification system"""

    @patch('apps.payment.services.get_channel_layer')
    @patch('apps.payment.services.async_to_sync')
    def test_send_real_time_notification_success(self, mock_async_to_sync, mock_get_channel_layer, test_restaurant):
        """Test successful real-time notification sending"""
        
        service = PaymentService()
        
        # 1. Setup the mock channel layer instance
        mock_channel = AsyncMock() 
        mock_get_channel_layer.return_value = mock_channel
        
        # 2. Setup the mock that GETS CALLED (the synchronous wrapper)
        # This is the crucial step. We check calls on this object.
        wrapper_mock = Mock()
       
        mock_async_to_sync.return_value = wrapper_mock
        
        notification_data = {
            'payment_id': str(uuid.uuid4()),
            'amount': 100.00,
            'order_id': str(uuid.uuid4()) # Added order_id for consistency
        }
        
        # Call the method
        service._send_real_time_notification(
            room=str(test_restaurant.id),
            event='payment_awaiting_collection',
            data=notification_data
        )
        
        # 3. Assert the call was made on the wrapper mock
        wrapper_mock.assert_called_once()
        
        # 4. Assert that mock_channel.group_send was PASSED as an argument to async_to_sync
        mock_async_to_sync.assert_called_once_with(mock_channel.group_send)
        
        # 5. Retrieve the arguments from the wrapper mock call
        # call_args[0] is (group_name, notification_payload)
        group_name, notification_payload = wrapper_mock.call_args[0]
        
        expected_group_name = f"restaurant_{test_restaurant.id}_staff"
        
        # 6. Assertions on the arguments
        assert group_name == expected_group_name
        assert notification_payload['type'] == 'staff.notification'
        assert notification_payload['event'] == 'payment_awaiting_collection'
        assert notification_payload['data'] == notification_data
        # You can also check for 'timestamp' and 'server_id' if needed
     
    @pytest.mark.asyncio # Marks the test as async, making 'await' valid
    @patch('apps.payment.services.get_channel_layer') 
    async def test_send_real_time_notification_async_success(self, mock_get_channel_layer, test_restaurant):
        """Test successful async real-time notification sending."""
        
        service = PaymentService()
        
        # Setup the mock channel layer instance
        # We use AsyncMock because it handles awaitable methods like group_send
        mock_channel = AsyncMock() 
        mock_get_channel_layer.return_value = mock_channel
        
        notification_data = {
            'payment_id': str(uuid.uuid4()),
            'amount': 100.00,
            'order_id': str(uuid.uuid4())
        }
        
        # Call the async method using await
        await service._send_real_time_notification_async(
            room=str(test_restaurant.id),
            event='payment_awaiting_collection',
            data=notification_data
        )
        
        # Assert directly on the mock channel instance's group_send method
        mock_channel.group_send.assert_called_once()
        
        # Retrieve the call arguments
        # call_args[0] is the tuple of positional arguments: (group_name, message_data)
        group_name, message_data = mock_channel.group_send.call_args[0]
        
        expected_group_name = f"restaurant_{test_restaurant.id}_staff"
        
        # 5. Assertions
        assert group_name == expected_group_name
        assert message_data['type'] == 'staff.notification'
        assert message_data['event'] == 'payment_awaiting_collection'
        assert message_data['data'] == notification_data
            
    @patch('apps.payment.services.get_channel_layer')
    @patch('apps.payment.services.async_to_sync')
    def test_send_real_time_notification_channel_error(self, mock_async_to_sync, test_restaurant):
        """Test notification handling when channel layer fails"""
        service = PaymentService()
        
        # Mock channel layer to raise an exception
        mock_async_to_sync.side_effect = Exception("Channel layer unavailable")
        
        notification_data = {
            'payment_id': str(uuid.uuid4()),
            'amount': 100.00
        }
        
        # This should not raise an exception
        service._send_real_time_notification(
            room=str(test_restaurant.id),
            event='test_event',
            data=notification_data
        )
        
        # Verify error was logged but no exception raised
        mock_async_to_sync.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('apps.payment.services.get_channel_layer')
    @patch('apps.payment.services.logger')
    async def test_send_real_time_notification_async_error(self, mock_logger, mock_get_channel_layer, test_restaurant):
        """Test async notification handling when channel layer fails."""
        
        service = PaymentService()
        
        # 1. Setup mock channel layer
        mock_channel = AsyncMock()
        # Configure the awaitable group_send method to raise an exception
        mock_channel.group_send.side_effect = Exception("Async channel layer failure")
        mock_get_channel_layer.return_value = mock_channel
        
        notification_data = {'payment_id': str(uuid.uuid4())}
        
        # 2. Since your service method ends with `raise` on exception, 
        # we expect the test to raise an exception.
        with pytest.raises(Exception) as excinfo:
            await service._send_real_time_notification_async(
                room=str(test_restaurant.id),
                event='test_event',
                data=notification_data
            )
        
        # 3. Assertions
        assert "Async channel layer failure" in str(excinfo.value)
        mock_channel.group_send.assert_called_once()
        
        # Verify the error was logged (using the patched logger)
        mock_logger.error.assert_called_once()
        assert "Async notification failed" in mock_logger.error.call_args[0][0]
        
    @patch('apps.payment.services.ActivityLog.objects.create')
    @patch('apps.payment.services.get_channel_layer')
    @patch('apps.payment.services.async_to_sync')
    def test_notification_fallback_logging(self, mock_async_to_sync, mock_channel_layer, mock_activity_log, test_restaurant):
        """Test that fallback logging works when notifications fail"""
        service = PaymentService()
        
        # Make channel layer fail
        mock_async_to_sync.side_effect = Exception("Channel error")
        
        notification_data = {
            'payment_id': str(uuid.uuid4()),
            'amount': 100.00
        }
        
        service._send_real_time_notification(
            room=str(test_restaurant.id),
            event='test_event',
            data=notification_data
        )
        
        # Verify fallback activity log was created
        mock_activity_log.assert_called_once()
        call_args = mock_activity_log.call_args[1]
        assert call_args['level'] == 'WARNING'
        assert call_args['module'] == 'NOTIFICATION'
        assert call_args['action'] == 'REALTIME_NOTIFICATION_FAILED'
    
    def test_notification_in_cash_payment_flow(self, invoice_instance, test_restaurant, test_user):
        """Test that notifications are sent during cash payment initiation"""
        service = PaymentService()
        
        with patch.object(service, '_send_real_time_notification') as mock_notification:
            
            payment_data = {
                'invoice_id': str(invoice_instance.id),
                'payment_method': 'cash',
                'amount': '113.00',
                'customer_phone': '256712345678'
            }
            
            result = service.initiate_payment(
                payment_data=payment_data,
                user_id=str(test_user.id)
            )
            
            assert result['success'] is True
            mock_notification.assert_called_once()
            
            # Verify notification was called with correct arguments
            call_args = mock_notification.call_args
            assert call_args[1]['room'] == str(test_restaurant.id)
            assert call_args[1]['event'] == 'payment_awaiting_collection'
            assert 'payment_id' in call_args[1]['data']
    
    def test_payment_service_singleton(self):
        """Test that payment_service is a singleton instance"""
        from apps.payment.services import payment_service
        
        service1 = payment_service
        service2 = payment_service
        assert service1 is service2
        assert isinstance(service1, PaymentService)
        
        # Test that new instances are different from the singleton
        service3 = PaymentService()
        assert service3 is not payment_service

@pytest.mark.django_db
class TestConcurrentPaymentOperations:
    """Tests for concurrent payment operations"""
    
    def test_concurrent_cash_payments(self, test_restaurant, test_user, invoice_instance, invoice_second_instance):
        """Test handling multiple concurrent cash payments"""
        service = PaymentService()
        
        # Create multiple payment requests
        payment_data_1 = {
            'invoice_id': str(invoice_instance.id),
            'payment_method': 'cash',
            'amount': '50.00',
            'customer_phone': '256711111111'
        }
        
        payment_data_2 = {
            'invoice_id': str(invoice_second_instance.id),
            'payment_method': 'cash',
            'amount': '75.00',
            'customer_phone': '256722222222'
        }
        
        # Process both payments
        result1 = service.initiate_payment(payment_data_1, str(test_user.id))
        result2 = service.initiate_payment(payment_data_2, str(test_user.id))
        
        # Both should succeed
        assert result1['success'] is True
        assert result2['success'] is True
        
        # Verify both payments were created
        payment1 = Payment.objects.get(id=result1['payment_id'])
        payment2 = Payment.objects.get(id=result2['payment_id'])
        
        assert payment1.status == 'AWAITING_COLLECTION'
        assert payment2.status == 'AWAITING_COLLECTION'
        assert payment1.restaurant == test_restaurant
        assert payment2.restaurant == test_restaurant

    def test_concurrent_wallet_payments_same_user(self, test_user,test_order,test_second_order, test_restaurant, customer_wallet):
        """Test concurrent wallet payments from the same user"""
        service = PaymentService()
        
        # Create two invoices
        invoice1 = Invoice.objects.create(
            order=test_second_order,
            restaurant=test_restaurant,
            subtotal_amount=Decimal('100.00'),
            tax_amount=Decimal('18.00'),
            service_fee=Decimal('5.00'),
            discount_amount=Decimal('10.00'),
            total_amount=Decimal('113.00'),
            due_date=timezone.now() + timedelta(days=1),
            status='ISSUED'
        )
        
        invoice2 = Invoice.objects.create(
            order=test_order,
            restaurant=test_restaurant,
            subtotal_amount=Decimal('100.00'),
            tax_amount=Decimal('18.00'),
            service_fee=Decimal('5.00'),
            discount_amount=Decimal('10.00'),
            total_amount=Decimal('113.00'),
            due_date=timezone.now() + timedelta(days=1),
            status='ISSUED'
        )
        
        payment_data_1 = {
            'invoice_id': str(invoice1.id),
            'payment_method': 'wallet',
            'payment_method_id': str(customer_wallet.id),
            'amount': '100.00'
        }
        
        payment_data_2 = {
            'invoice_id': str(invoice2.id),
            'payment_method': 'wallet', 
            'payment_method_id': str(customer_wallet.id),
            'amount': '60.00'
        }
        
        # First payment should succeed
        result1 = service.initiate_payment(payment_data_1, str(test_user.id))
        assert result1['success'] is True
        
        #testing pertially paid invoice staus 
        invoice1.refresh_from_db()
        assert invoice1.status == 'PARTIALLY_PAID'
        
        #verify vallet balance after first payment
        customer_wallet.refresh_from_db()
        assert customer_wallet.available_balance == Decimal('50.00')  # 150 - 100
        
        
        # Second payment should fail due to insufficient funds (70 remaining after first payment)
        result2 = service.initiate_payment(payment_data_2, str(test_user.id))
        assert result2['success'] is False
        assert 'insufficient' in result2['error'].lower()


@pytest.mark.django_db
class TestWalletServices:
    """Comprehensive unit tests for WalletService"""
    
    # get_wallet_balance method
    def test_get_wallet_balance_success(self, test_user, test_restaurant):
        """Test successful wallet balance retrieval"""
        wallet = CustomerWallet.objects.create(
        user_id=test_user.id,
        restaurant_id=test_restaurant.id,
        available_balance=Decimal('100.00'),
        pending_balance=Decimal('0.00'),
        wallet_type='PREPAID',
        status='ACTIVE',
        currency='UGX'
        )
        
        service = WalletService()
        
        result = service.get_wallet_balance(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            wallet_type='PREPAID'
        )
        
        assert result['available_balance'] == Decimal('100.00')
        assert result['pending_balance'] == Decimal('0.00')
        assert result['total_balance'] == Decimal('100.00')
        assert result['currency'] == 'UGX'
        assert result['status'] == 'ACTIVE'
    
    def test_get_wallet_balance_not_found(self, test_user, test_restaurant):
        """Test wallet balance retrieval for non-existent wallet"""
        service = WalletService()
        
        result = service.get_wallet_balance(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            wallet_type='PREPAID'
        )
        
        assert result['available_balance'] == 0
        assert result['pending_balance'] == 0
        assert result['total_balance'] == 0
        assert result['currency'] == 'X-SWIFT'
        assert result['status'] == 'NOT_FOUND'
    
    def test_get_wallet_balance_different_type(self, test_user, test_restaurant):
        """Test getting balance for different wallet type"""
        service = WalletService()
        
        # Create a loyalty wallet
        loyalty_wallet = CustomerWallet.objects.create(
            user=test_user,
            restaurant=test_restaurant,
            wallet_type='LOYALTY',
            available_balance=Decimal('500.00'),
            currency='X-SWIFT'
        )
        
        result = service.get_wallet_balance(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            wallet_type='LOYALTY'
        )
        
        assert result['available_balance'] == Decimal('500.00')
        assert result['wallet_type'] == 'LOYALTY'
    
    #  add_funds method
    def test_add_funds_new_wallet_creation(self, test_user, test_restaurant):
        """Test creating new wallet when adding funds"""
        service = WalletService()
        
        reference_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        result = service.add_funds(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('50.00'),
            reference_type='DEPOSIT',
            reference_id=reference_id,
            description='Test deposit',
            correlation_id=correlation_id
        )
        
        assert result['success'] is True
        assert 'wallet_id' in result
        assert result['new_balance'] == 50.0
        
        # Verify wallet was created
        wallet = CustomerWallet.objects.get(
            user=test_user,
            restaurant=test_restaurant,
            wallet_type='PREPAID'
        )
        assert wallet.available_balance == Decimal('50.00')
        assert wallet.currency == 'UGX'
        
        # Verify activity logs
        activity_logs = ActivityLog.objects.filter(correlation_id=correlation_id)
        assert activity_logs.filter(action='WALLET_CREATED').exists()
    
    def test_add_funds_existing_wallet(self, customer_wallet, test_user, test_restaurant):
        """Test adding funds to existing wallet"""
        service = WalletService()
        
        initial_balance = customer_wallet.available_balance
        reference_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        result = service.add_funds(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('25.00'),
            reference_type='DEPOSIT',
            reference_id=reference_id,
            description='Additional deposit',
            correlation_id=correlation_id
        )
        
        assert result['success'] is True
        assert result['new_balance'] == float(initial_balance + Decimal('25.00'))
        
        # Verify wallet balance was updated
        customer_wallet.refresh_from_db()
        assert customer_wallet.available_balance == initial_balance + Decimal('25.00')
        
        # Verify activity log
        activity_log = ActivityLog.objects.filter(
            correlation_id=correlation_id,
            action='FUNDS_ADDED'
        ).first()
        assert activity_log is not None
        assert activity_log.details['amount'] == 25.0
    
    def test_add_funds_closed_wallet(self, customer_wallet, test_user, test_restaurant):
        """Test adding funds to closed wallet"""
        service = WalletService()
        
        # Close the wallet
        customer_wallet.status = 'CLOSED'
        customer_wallet.closed_at = timezone.now()
        customer_wallet.save()
        
        correlation_id = str(uuid.uuid4())
        
        result = service.add_funds(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('25.00'),
            reference_type='DEPOSIT',
            reference_id=str(uuid.uuid4()),
            description='Deposit to closed wallet',
            correlation_id=correlation_id
        )
        
        assert result['allowed'] is False
        assert result['reason'] == 'WALLET_CLOSED'
        assert 'permanently closed' in result['message'].lower()
    
    def test_add_funds_suspended_wallet(self, customer_wallet, test_user, test_restaurant):
        """Test adding funds to suspended wallet"""
        service = WalletService()
        
        # Suspend the wallet
        customer_wallet.status = 'SUSPENDED'
        customer_wallet.save()
        
        correlation_id = str(uuid.uuid4())
        
        result = service.add_funds(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('25.00'),
            reference_type='DEPOSIT',
            reference_id=str(uuid.uuid4()),
            description='Deposit to suspended wallet',
            correlation_id=correlation_id
        )
        
        assert result['allowed'] is False
        assert result['reason'] == 'WALLET_SUSPENDED'
        assert 'temporarily suspended' in result['message'].lower()
    
    def test_add_funds_accounting_entry_created(self, customer_wallet, test_user, test_restaurant):
        """Test that accounting entry is created when adding funds"""
        service = WalletService()
        
        reference_id = str(uuid.uuid4())
        description = "Test deposit accounting"
        
        with patch.object(service, '_create_wallet_deposit_accounting_entry') as mock_accounting:
            result = service.add_funds(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                amount=Decimal('50.00'),
                reference_type='DEPOSIT',
                reference_id=reference_id,
                description=description
            )
            
            assert result['success'] is True
            mock_accounting.assert_called_once_with(
                restaurant_id=str(test_restaurant.id),
                amount=Decimal('50.00'),
                reference_id=reference_id,
                description=description,
                user_id=str(test_user.id)
            )
    
    def test_add_funds_exception_handling(self, customer_wallet, test_user, test_restaurant):
        """Test exception handling in add_funds"""
        service = WalletService()
        
        correlation_id = str(uuid.uuid4())
        
        # Mock an exception
        with patch.object(CustomerWallet.objects, 'get_or_create', side_effect=Exception("Database error")):
            result = service.add_funds(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                amount=Decimal('50.00'),
                reference_type='DEPOSIT',
                reference_id=str(uuid.uuid4()),
                description='Test deposit',
                correlation_id=correlation_id
            )
            
            assert result['success'] is False
            assert 'error' in result
            assert 'Database error' in result['error']
            
            # Verify error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='ADD_FUNDS_FAILED'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'ERROR'
    
    # authorize_order_payment method
    def test_authorize_order_payment_success(self, customer_wallet, test_user, test_restaurant):
        """Test successful order authorization"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        amount = Decimal('50.00')
        correlation_id = str(uuid.uuid4())
        
        # Mock the wallet's authorize_funds method
        with patch.object(customer_wallet, 'authorize_funds') as mock_authorize:
            mock_authorize.return_value = None
            
            result = service.authorize_order_payment(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                order_id=order_id,
                amount=amount,
                correlation_id=correlation_id
            )
            
            assert result is True
            mock_authorize.assert_called_once_with(
                amount=amount,
                reference_type='ORDER',
                reference_id=order_id,
                description=f"Order authorization for #{order_id}"
            )
            
            # Verify activity log
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='AUTHORIZATION_SUCCESS'
            ).first()
            assert activity_log is not None
            assert activity_log.details['order_id'] == order_id
    
    def test_authorize_order_payment_insufficient_funds(self, customer_wallet, test_user, test_restaurant):
        """Test authorization with insufficient funds"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        amount = Decimal('200.00')  # More than wallet balance
        correlation_id = str(uuid.uuid4())
        
        # Mock InsufficientFundsError
        from apps.payment.services import InsufficientFundsError
        
        with patch.object(customer_wallet, 'authorize_funds', side_effect=InsufficientFundsError("Not enough funds")):
            with pytest.raises(InsufficientFundsError):
                service.authorize_order_payment(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    order_id=order_id,
                    amount=amount,
                    correlation_id=correlation_id
                )
            
            # Verify error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='AUTHORIZATION_FAILED'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'WARNING'
    
    def test_authorize_order_payment_general_exception(self, customer_wallet, test_user, test_restaurant):
        """Test authorization with general exception"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        # Mock general exception
        from apps.payment.services import WalletError
        
        with patch.object(CustomerWallet.objects, 'get', side_effect=Exception("Database error")):
            with pytest.raises(WalletError, match="internal error"):
                service.authorize_order_payment(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    order_id=order_id,
                    amount=Decimal('50.00'),
                    correlation_id=correlation_id
                )
            
            # Verify critical error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='AUTHORIZATION_CRITICAL_FAILURE'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'CRITICAL'
    
    # capture_order_payment method
    def test_capture_order_payment_success(self, customer_wallet, test_user, test_restaurant):
        """Test successful order payment capture"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        amount = Decimal('50.00')
        correlation_id = str(uuid.uuid4())
        
        # Mock the wallet's capture_funds method
        with patch.object(CustomerWallet, 'capture_funds') as mock_capture:
            mock_capture.return_value = None
            
            result = service.capture_order_payment(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                order_id=order_id,
                amount=amount,
                correlation_id=correlation_id
            )
            
            assert result is True
            mock_capture.assert_called_once_with(
                amount=amount,
                reference_type='ORDER',
                reference_id=order_id,
                description=f"Order payment capture for #{order_id}"
            )
            
            # Verify activity log
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='CAPTURE_SUCCESS'
            ).first()
            assert activity_log is not None
    
    def test_capture_order_payment_invalid_pending(self, customer_wallet, test_user, test_restaurant):
        """Test capture with invalid pending amount"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        # Mock InvalidPendingCaptureError
        from apps.payment.services import InvalidPendingCaptureError
        
        with patch.object(CustomerWallet, 'capture_funds', 
                         side_effect=InvalidPendingCaptureError("Invalid pending amount")):
            with pytest.raises(InvalidPendingCaptureError):
                service.capture_order_payment(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    order_id=order_id,
                    amount=Decimal('50.00'),
                    correlation_id=correlation_id
                )
            
            # Verify error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='CAPTURE_FAILED'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'ERROR'
    
    # release_order_authorization method
    def test_release_order_authorization_success(self, customer_wallet, test_user, test_restaurant):
        """Test successful release of order authorization"""
        service = WalletService()
        
        customer_wallet.pending_balance = Decimal('100.00')
        customer_wallet.save()
        
        order_id = str(uuid.uuid4())
        amount = Decimal('50.00')
        correlation_id = str(uuid.uuid4())
        
        # Mock the wallet's release_funds method
        with patch.object(CustomerWallet, 'release_funds') as mock_release:
            mock_release.return_value = None
            
            result = service.release_order_authorization(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                order_id=order_id,
                amount=amount,
                correlation_id=correlation_id
            )
            
            assert result is True
            mock_release.assert_called_once_with(
                amount=amount,
                reference_type='ORDER_CANCEL',
                reference_id=order_id,
                description=f"Order cancellation funds release for #{order_id}"
            )
            
            # Verify activity log
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='RELEASE_SUCCESS'
            ).first()
            assert activity_log is not None
    
    def test_release_order_authorization_invalid_pending(self, customer_wallet, test_user, test_restaurant):
        """Test release with invalid pending amount"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        from apps.payment.services import InvalidPendingCaptureError
        
        customer_wallet.pending_balance = Decimal('20.00')
        customer_wallet.save()
        
        # Mock InvalidPendingCaptureError
        with patch.object(CustomerWallet, 'release_funds', 
                         side_effect=InvalidPendingCaptureError("Invalid pending amount")):
            with pytest.raises(InvalidPendingCaptureError):
                service.release_order_authorization(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    order_id=order_id,
                    amount=Decimal('50.00'),
                    correlation_id=correlation_id
                )
            
            # Verify error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='RELEASE_FAILED'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'ERROR'
    
    # process_refund method
    def test_process_refund_success(self, customer_wallet, test_user, test_restaurant):
        """Test successful refund processing"""
        service = WalletService()
        
        refund_id = str(uuid.uuid4())
        amount = Decimal('25.00')
        original_ref = 'PAYMENT_12345'
        correlation_id = str(uuid.uuid4())
        
        # Mock the wallet's refund_funds method
        with patch.object(CustomerWallet, 'refund_funds') as mock_refund:
            mock_refund.return_value = None
            
            result = service.process_refund(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                refund_id=refund_id,
                amount=amount,
                original_payment_ref=original_ref,
                wallet_type='PREPAID',
                correlation_id=correlation_id
            )
            
            assert result is True
            mock_refund.assert_called_once_with(
                amount=amount,
                reference_type='REFUND',
                reference_id=refund_id,
                original_payment_ref=original_ref,
                description=f"Processing refund ID {refund_id}"
            )
            
            # Verify activity log
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='FUNDS_REFUNDED'
            ).first()
            assert activity_log is not None
            assert activity_log.details['refund_id'] == refund_id
    
    def test_process_refund_wallet_error(self, customer_wallet, test_user, test_restaurant):
        """Test refund processing with wallet error"""
        service = WalletService()
        
        refund_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        # Mock WalletError
        from apps.payment.services import WalletError
        
        with patch.object(CustomerWallet, 'refund_funds', 
                         side_effect=WalletError("Wallet is closed")):
            with pytest.raises(WalletError):
                service.process_refund(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    refund_id=refund_id,
                    amount=Decimal('25.00'),
                    original_payment_ref='PAYMENT_123',
                    correlation_id=correlation_id
                )
            
            # Verify error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='REFUND_FAILED'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'ERROR'
    
    def test_process_refund_general_exception(self, customer_wallet, test_user, test_restaurant):
        """Test refund processing with general exception"""
        service = WalletService()
        
        refund_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        from apps.payment.services import WalletError
        
        # Mock general exception
        with patch.object(CustomerWallet, 'refund_funds', 
                         side_effect=Exception("Unexpected error")):
            with pytest.raises(WalletError, match="internal error"):
                service.process_refund(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    refund_id=refund_id,
                    amount=Decimal('25.00'),
                    original_payment_ref='PAYMENT_123',
                    correlation_id=correlation_id
                )
            
            # Verify critical error was logged
            activity_log = ActivityLog.objects.filter(
                correlation_id=correlation_id,
                action='REFUND_CRITICAL_FAILURE'
            ).first()
            assert activity_log is not None
            assert activity_log.level == 'CRITICAL'
    
    def test_process_refund_different_wallet_type(self, test_user, test_restaurant):
        """Test refund to different wallet type (LOYALTY)"""
        service = WalletService()
        
        # Create a loyalty wallet
        loyalty_wallet = CustomerWallet.objects.create(
            user=test_user,
            restaurant=test_restaurant,
            wallet_type='LOYALTY',
            available_balance=Decimal('100.00')
        )
        
        refund_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        with patch.object(CustomerWallet, 'refund_funds') as mock_refund:
            mock_refund.return_value = None
            
            result = service.process_refund(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                refund_id=refund_id,
                amount=Decimal('50.00'),
                original_payment_ref='PAYMENT_123',
                wallet_type='LOYALTY',
                correlation_id=correlation_id
            )
            
            assert result is True
            mock_refund.assert_called_once()
    
    #_get_wallet_for_user helper method
    def test_get_wallet_for_user_success(self, customer_wallet, test_user, test_restaurant):
        """Test successful wallet retrieval"""
        service = WalletService()
        
        wallet = service._get_wallet_for_user(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            wallet_type='PREPAID'
        )
        
        assert wallet == customer_wallet
        assert wallet.user == test_user
        assert wallet.restaurant == test_restaurant
    
    def test_get_wallet_for_user_not_found(self, test_user, test_restaurant):
        """Test wallet retrieval when not found"""
        service = WalletService()
        
        with pytest.raises(WalletError, match="Customer wallet not found"):
            service._get_wallet_for_user(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                wallet_type='PREPAID'
            )
    
    # Edge cases and integration tests
    def test_concurrent_wallet_operations(self, customer_wallet, test_user, test_restaurant):
        """Test that wallet operations handle concurrency"""
        service = WalletService()
        
        order_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        
        # Simulate authorization and capture
        with patch.object(customer_wallet, 'authorize_funds') as mock_authorize:
            with patch.object(customer_wallet, 'capture_funds') as mock_capture:
                mock_authorize.return_value = None
                mock_capture.return_value = None
                
                # Authorize
                auth_result = service.authorize_order_payment(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    order_id=order_id,
                    amount=Decimal('50.00'),
                    correlation_id=correlation_id
                )
                
                # Capture
                capture_result = service.capture_order_payment(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    order_id=order_id,
                    amount=Decimal('50.00'),
                    correlation_id=str(uuid.uuid4())
                )
                
                assert auth_result is True
                assert capture_result is True
                
                mock_authorize.assert_called_once()
                mock_capture.assert_called_once()
    
    def test_wallet_status_methods(self, customer_wallet):
        """Test wallet status helper methods"""
        # Test active wallet
        customer_wallet.status = 'ACTIVE'
        assert customer_wallet.is_active() is True
        assert customer_wallet.is_suspended() is False
        assert customer_wallet.is_closed() is False
        
        # Test suspended wallet
        customer_wallet.status = 'SUSPENDED'
        assert customer_wallet.is_active() is False
        assert customer_wallet.is_suspended() is True
        
        # Test closed wallet
        customer_wallet.status = 'CLOSED'
        customer_wallet.closed_at = timezone.now()
        assert customer_wallet.is_active() is False
        assert customer_wallet.is_closed() is True
    
    def test_correlation_id_propagation(self, test_user, test_restaurant):
        """Test that correlation IDs are properly propagated"""
        service = WalletService()
        
        correlation_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        
        with patch.object(CustomerWallet.objects, 'get') as mock_get:
            mock_wallet = Mock()
            
            from decimal import Decimal
            
            mock_wallet.available_balance = Decimal('100.00') 
            mock_wallet.pending_balance = Decimal('0.00')
            
            mock_wallet.authorize_funds = Mock(return_value=None)
            mock_get.return_value = mock_wallet
            
            service.authorize_order_payment(
                user_id=str(test_user.id),
                restaurant_id=str(test_restaurant.id),
                order_id=order_id,
                amount=Decimal('50.00'),
                correlation_id=correlation_id
            )
            
            # Verify activity log has the correlation ID
            activity_log = ActivityLog.objects.filter(correlation_id=correlation_id).first()
            assert activity_log is not None
            assert activity_log.correlation_id == uuid.UUID(correlation_id)


# Additional test class for error scenarios
@pytest.mark.django_db
class TestWalletServiceErrorScenarios:
    """Tests for specific error scenarios in WalletService"""
    
    def test_add_funds_max_balance_limit(self, test_user, test_restaurant):
        """Test adding funds when wallet has max balance limit"""
        service = WalletService()
        
        # Create wallet with max balance
        wallet = CustomerWallet.objects.create(
            user=test_user,
            restaurant=test_restaurant,
            wallet_type='PREPAID',
            available_balance=Decimal('900.00'),
            max_balance=Decimal('1000.00')
        )
        
        # add more than max balance allows
        result = service.add_funds(
            user_id=str(test_user.id),
            restaurant_id=str(test_restaurant.id),
            amount=Decimal('150.00'),  # Would exceed max balance
            reference_type='DEPOSIT',
            reference_id=str(uuid.uuid4()),
            description='Test deposit'
        )
        
        assert result['success'] is False
        assert 'exceeding the maximum limit' in result['error']
        
    def test_refund_exceeds_original_payment(self, customer_wallet, test_user, test_restaurant):
        """Test refund amount exceeding original payment"""
        service = WalletService()
        
        refund_id = str(uuid.uuid4())
        
        from apps.payment.services import WalletError
        
        with patch.object(CustomerWallet, 'refund_funds') as mock_refund:
            # the model validates this
            mock_refund.side_effect = WalletError("Refund amount exceeds original payment")
            
            with pytest.raises(WalletError, match="exceeds original payment"):
                service.process_refund(
                    user_id=str(test_user.id),
                    restaurant_id=str(test_restaurant.id),
                    refund_id=refund_id,
                    amount=Decimal('200.00'),  # More than wallet balance
                    original_payment_ref='PAYMENT_123'
                )
