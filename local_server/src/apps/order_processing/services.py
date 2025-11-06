import logging
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.db import transaction

from apps.order_processing.models import OfflineOrder, OrderCRDTState
from apps.core.models import SyncQueue, Restaurant
from apps.otp_service.services import OTPService
from apps.payment.services import PaymentService

logger = logging.getLogger('dineswift')

class OrderProcessingService:
    def __init__(self):
        self.otp_service = OTPService()
        self.payment_service = PaymentService()
    
    def create_offline_order(self, restaurant_id: str, order_data: dict) -> dict:
        """Create an offline order with full validation and processing"""
        try:
            # Validate input
            if not order_data.get('items'):
                return {
                    'success': False,
                    'error': 'Order must contain at least one item'
                }
            
            # Get restaurant
            try:
                restaurant = Restaurant.objects.get(id=restaurant_id)
            except Restaurant.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Restaurant not found'
                }
            
            with transaction.atomic():
                # Calculate totals
                subtotal = self.calculate_subtotal(order_data['items'])
                tax_amount = self.calculate_tax(subtotal)
                total_amount = subtotal + tax_amount
                                
                # Generate local order ID
                local_order_id = self.generate_local_order_id(restaurant)
                
                # Create order
                order = OfflineOrder.objects.create(
                    restaurant=restaurant,
                    local_order_id=local_order_id,
                    order_items=order_data['items'],
                    total_amount=total_amount,
                    tax_amount=tax_amount,
                    table_id=order_data.get('table_id'),
                    customer_id=order_data.get('customer_id'),
                    special_instructions=order_data.get('special_instructions', ''),
                    estimated_preparation_time=order_data.get('estimated_preparation_time'),
                    order_status='PENDING',
                    sync_status='PENDING_SYNC'
                )
                
                # Generate OTP
                otp_code = self.otp_service.generate_otp(order_id=str(order.id))
                
                # Create CRDT state for conflict resolution
                OrderCRDTState.objects.create(
                    order=order,
                    vector_clock={'local': 1, 'cloud': 0},
                    last_operation='ORDER_CREATE',
                    operation_timestamp=timezone.now()
                )
                
                # Create sync queue entry
                SyncQueue.objects.create(
                    restaurant=restaurant,
                    sync_type='ORDER_CREATE',
                    payload={
                        'local_order_id': str(order.id),
                        'order_data': {
                            'items': order_data['items'],
                            'table_id': order_data.get('table_id'),
                            'total_amount': float(total_amount),
                            'tax_amount': float(tax_amount)
                        }
                    }
                )
                
                logger.info(f"Order created successfully: {local_order_id} for restaurant {restaurant_id}")
                
                return {
                    'success': True,
                    'order_id': str(order.id),
                    'local_order_id': local_order_id,
                    'otp_code': otp_code,
                    'total_amount': total_amount,
                    'tax_amount': tax_amount
                }
                
        except Exception as e:
            logger.error(f"Order creation failed: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'Order creation failed',
                'details': str(e)
            }
    
    def update_order_status(self, order_id: str, new_status: str, notes: str = '') -> bool:
        """Update order status with validation and audit trail"""
        try:
            order = OfflineOrder.objects.get(id=order_id)
            
            # Validate status transition
            if not self.is_valid_status_transition(order.order_status, new_status):
                logger.warning(
                    f"Invalid status transition for order {order_id}: "
                    f"{order.order_status} -> {new_status}"
                )
                return False
            
            with transaction.atomic():
                # Update order
                previous_status = order.order_status
                order.order_status = new_status
                
                # Set timestamps based on status
                current_time = timezone.now()
                if new_status == 'PREPARING' and not order.preparation_started_at:
                    order.preparation_started_at = current_time
                elif new_status == 'COMPLETED' and not order.completed_at:
                    order.completed_at = current_time
                    # Calculate actual preparation time
                    if order.preparation_started_at:
                        prep_time = (current_time - order.preparation_started_at).total_seconds() / 60
                        order.actual_preparation_time = int(prep_time)
                
                order.save()
                
                # Update CRDT state
                try:
                    crdt_state = OrderCRDTState.objects.get(order=order)
                    crdt_state.vector_clock['local'] = crdt_state.vector_clock.get('local', 0) + 1
                    crdt_state.last_operation = 'STATUS_UPDATE'
                    crdt_state.operation_timestamp = current_time
                    crdt_state.save()
                except OrderCRDTState.DoesNotExist:
                    # Create CRDT state if it doesn't exist
                    OrderCRDTState.objects.create(
                        order=order,
                        vector_clock={'local': 1, 'cloud': 0},
                        last_operation='STATUS_UPDATE',
                        operation_timestamp=current_time
                    )
                
                # Create sync queue entry
                SyncQueue.objects.create(
                    restaurant=order.restaurant,
                    sync_type='ORDER_UPDATE',
                    payload={
                        'local_order_id': str(order.id),
                        'previous_status': previous_status,
                        'new_status': new_status,
                        'notes': notes,
                        'timestamp': current_time.isoformat()
                    }
                )
                
                logger.info(
                    f"Order status updated: {order.local_order_id} "
                    f"from {previous_status} to {new_status}"
                )
                
                return True
            
        except OfflineOrder.DoesNotExist:
            logger.error(f"Order not found: {order_id}")
            return False
        except Exception as e:
            logger.error(f"Status update failed for order {order_id}: {str(e)}", exc_info=True)
            return False
    
    def calculate_subtotal(self, items: list) -> Decimal:
        """Calculate order subtotal including modifiers"""
        subtotal = Decimal('0.00')
        
        for item in items:
            # Validate required fields
            if 'price' not in item or 'quantity' not in item:
                raise ValueError("Item missing price or quantity")
            
            price = Decimal(str(item['price']))
            quantity = int(item['quantity'])
            
            # Validate positive values
            if price < Decimal('0.00'):
                raise ValueError(f"Invalid price for item: {item.get('name', 'Unknown')}")
            if quantity <= 0:
                raise ValueError(f"Invalid quantity for item: {item.get('name', 'Unknown')}")
            
            item_total = price * quantity
            subtotal += item_total
            
            # Add modifiers if any
            for modifier in item.get('modifiers', []):
                modifier_price = Decimal(str(modifier.get('price', '0.00')))
                if modifier_price < Decimal('0.00'):
                    raise ValueError(f"Invalid modifier price for {modifier.get('name', 'Unknown')}")
                subtotal += modifier_price * quantity
        
        return subtotal.quantize(Decimal('0.01'))
    
    def calculate_tax(self, subtotal: Decimal, tax_rate: float = 0.08) -> Decimal:
        """Calculate tax amount with configurable tax rate"""
        if subtotal < Decimal('0.00'):
            raise ValueError("Subtotal cannot be negative")
        
        tax_amount = subtotal * Decimal(str(tax_rate))
        return tax_amount.quantize(Decimal('0.01'))
    
    def generate_local_order_id(self, restaurant: Restaurant) -> str:
        """Generate unique local order ID with restaurant prefix"""
        from datetime import datetime
        
        # Get restaurant prefix (first 3 chars of name)
        prefix = restaurant.name[:3].upper() if restaurant.name else 'ORD'
        
        # Get current timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # Get sequence number for today
        today = timezone.now().date()
        today_orders_count = OfflineOrder.objects.filter(
            restaurant=restaurant,
            created_at__date=today
        ).count()
        
        sequence = today_orders_count + 1
        
        return f"{prefix}-{timestamp}-{sequence:04d}"
    
    def is_valid_status_transition(self, current_status: str, new_status: str) -> bool:
        """Validate order status transition with business rules"""
        valid_transitions = {
            'PENDING': ['CONFIRMED', 'CANCELLED', 'PAYMENT_FAILED'],
            'CONFIRMED': ['PREPARING', 'CANCELLED'],
            'PREPARING': ['READY', 'CANCELLED'],
            'READY': ['COMPLETED'],
            'COMPLETED': [],  # Final state
            'CANCELLED': [],  # Final state
            'PAYMENT_FAILED': ['CANCELLED']
        }
        
        return new_status in valid_transitions.get(current_status, [])
    
    def get_order_details(self, order_id: str) -> dict:
        """Get complete order details with related data"""
        try:
            order = OfflineOrder.objects.select_related('restaurant', 'payment').get(id=order_id)
            
            return {
                'success': True,
                'order': {
                    'id': str(order.id),
                    'local_order_id': order.local_order_id,
                    'supabase_order_id': str(order.supabase_order_id) if order.supabase_order_id else None,
                    'restaurant_name': order.restaurant.name,
                    'table_id': str(order.table_id) if order.table_id else None,
                    'order_items': order.order_items,
                    'total_amount': float(order.total_amount),
                    'tax_amount': float(order.tax_amount),
                    'special_instructions': order.special_instructions,
                    'order_status': order.order_status,
                    'sync_status': order.sync_status,
                    'estimated_preparation_time': order.estimated_preparation_time,
                    'actual_preparation_time': order.actual_preparation_time,
                    'preparation_started_at': order.preparation_started_at.isoformat() if order.preparation_started_at else None,
                    'completed_at': order.completed_at.isoformat() if order.completed_at else None,
                    'created_at': order.created_at.isoformat(),
                    'updated_at': order.updated_at.isoformat()
                }
            }
            
        except OfflineOrder.DoesNotExist:
            return {
                'success': False,
                'error': 'Order not found'
            }
        except Exception as e:
            logger.error(f"Failed to get order details: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'Failed to retrieve order details'
            }
    
    def cancel_order(self, order_id: str, reason: str = '') -> bool:
        """Cancel an order with proper cleanup"""
        try:
            return self.update_order_status(
                order_id, 
                'CANCELLED', 
                f"Order cancelled: {reason}"
            )
        except Exception as e:
            logger.error(f"Order cancellation failed: {str(e)}", exc_info=True)
            return False
    
    def get_restaurant_orders(self, restaurant_id: str, status: str = None) -> dict:
        """Get all orders for a restaurant with optional status filter"""
        try:
            queryset = OfflineOrder.objects.filter(restaurant_id=restaurant_id)
            
            if status:
                queryset = queryset.filter(order_status=status)
            
            orders = queryset.order_by('-created_at')
            
            return {
                'success': True,
                'orders': [
                    {
                        'id': str(order.id),
                        'local_order_id': order.local_order_id,
                        'table_id': str(order.table_id) if order.table_id else None,
                        'total_amount': float(order.total_amount),
                        'order_status': order.order_status,
                        'sync_status': order.sync_status,
                        'created_at': order.created_at.isoformat()
                    }
                    for order in orders
                ],
                'count': orders.count()
            }
            
        except Exception as e:
            logger.error(f"Failed to get restaurant orders: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'Failed to retrieve orders'
            }
    
    def create_order_with_payment(self, restaurant_id: str, order_data: dict) -> dict:
        """Complete order flow with payment integration"""
        try:
            # Validate payment method requirements
            payment_method = order_data.get('payment_method', 'momo')
            if payment_method == 'momo' and not order_data.get('customer_phone'):
                return {
                    'success': False,
                    'error': 'Phone number is required for Momo payments'
                }
            
            # 1. Create order locally (UC-LOCAL-ORDER-104)
            order_result = self.create_offline_order(restaurant_id, order_data)
            
            if not order_result['success']:
                return order_result
            
            # 2. Initiate payment (MOBILE-APP-FR-004-P1)
            payment_data = {
                'order_id': order_result['order_id'],
                'amount': float(order_result['total_amount']),
                'phone': order_data.get('customer_phone'),
                'payment_method': payment_method,
                'restaurant_id': restaurant_id
            }
            
            payment_result = self.payment_service.initiate_payment(payment_data)
            
            if not payment_result['success']:
                # Mark order as payment failed
                self.update_order_status(
                    order_result['order_id'], 
                    'PAYMENT_FAILED',
                    f"Payment initiation failed: {payment_result.get('error', 'Unknown error')}"
                )
                return {
                    'success': False,
                    'error': 'Payment initiation failed',
                    'payment_error': payment_result.get('error'),
                    'order_id': order_result['order_id']  # Return order ID for reference
                }
            
            # 3. Return combined result
            return {
                'success': True,
                'order_id': order_result['order_id'],
                'local_order_id': order_result['local_order_id'],
                'payment_id': payment_result['payment_id'],
                'otp_code': order_result['otp_code'],
                'total_amount': float(order_result['total_amount']),
                'payment_status': payment_result['status'],
                'next_step': 'wait_for_payment_confirmation',
                'payment_gateway_data': payment_result.get('gateway_data', {})
            }
            
        except Exception as e:
            logger.error(f"Order with payment failed: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'Order creation failed',
                'details': str(e)
            }


class ConflictResolutionService:
    """Service for handling CRDT conflict resolution"""
    
    def resolve_order_conflict(self, local_order: dict, remote_order: dict) -> dict:
        """Resolve conflicts between local and remote order versions"""
        try:
            # Compare timestamps - most recent wins for most fields
            local_time = local_order.get('last_updated')
            remote_time = remote_order.get('last_updated')
            
            # Use the order with the latest timestamp as base
            if remote_time > local_time:
                base_order = remote_order.copy()
                other_order = local_order
            else:
                base_order = local_order.copy()
                other_order = remote_order
            
            # Merge items using LWW (Last Write Wins) for individual items
            merged_items = self.merge_order_items(
                local_order.get('items', []),
                remote_order.get('items', [])
            )
            
            base_order['items'] = merged_items
            base_order['version'] = max(local_order.get('version', 0), remote_order.get('version', 0)) + 1
            base_order['last_updated'] = max(local_time, remote_time) if local_time and remote_time else base_order['last_updated']
            
            return base_order
            
        except Exception as e:
            logger.error(f"Conflict resolution failed: {str(e)}", exc_info=True)
            # Fallback: use remote order
            return remote_order
    
    def merge_order_items(self, local_items: list, remote_items: list) -> list:
        """Merge order items from different sources"""
        merged_items = []
        all_items = {}
        
        # Index items by ID for merging
        for item in local_items + remote_items:
            item_id = item.get('id')
            if item_id:
                # Use the item with the latest timestamp, or local if no timestamp
                existing_item = all_items.get(item_id)
                if not existing_item or item.get('last_updated', '') > existing_item.get('last_updated', ''):
                    all_items[item_id] = item
        
        return list(all_items.values())


class OrderValidationService:
    """Service for order validation"""
    
    def validate_order_data(self, order_data: dict) -> dict:
        """Validate order data before processing"""
        errors = []
        
        # Validate items
        if not order_data.get('items'):
            errors.append("Order must contain at least one item")
        else:
            for i, item in enumerate(order_data['items']):
                item_errors = self.validate_order_item(item, i)
                errors.extend(item_errors)
        
        # Validate payment method if specified
        payment_method = order_data.get('payment_method')
        if payment_method == 'momo' and not order_data.get('customer_phone'):
            errors.append("Phone number is required for Momo payments")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_order_item(self, item: dict, index: int) -> list:
        """Validate individual order item"""
        errors = []
        
        if not item.get('id'):
            errors.append(f"Item {index + 1}: Missing ID")
        
        if not item.get('name'):
            errors.append(f"Item {index + 1}: Missing name")
        
        try:
            price = Decimal(str(item.get('price', 0)))
            if price < Decimal('0.00'):
                errors.append(f"Item {index + 1}: Price cannot be negative")
        except (TypeError, ValueError):
            errors.append(f"Item {index + 1}: Invalid price format")
        
        try:
            quantity = int(item.get('quantity', 0))
            if quantity <= 0:
                errors.append(f"Item {index + 1}: Quantity must be positive")
        except (TypeError, ValueError):
            errors.append(f"Item {index + 1}: Invalid quantity format")
        
        # Validate modifiers
        for j, modifier in enumerate(item.get('modifiers', [])):
            modifier_errors = self.validate_modifier(modifier, index, j)
            errors.extend(modifier_errors)
        
        return errors
    
    def validate_modifier(self, modifier: dict, item_index: int, modifier_index: int) -> list:
        """Validate item modifier"""
        errors = []
        
        if not modifier.get('name'):
            errors.append(f"Item {item_index + 1} modifier {modifier_index + 1}: Missing name")
        
        try:
            price = Decimal(str(modifier.get('price', 0)))
            if price < Decimal('0.00'):
                errors.append(f"Item {item_index + 1} modifier {modifier_index + 1}: Price cannot be negative")
        except (TypeError, ValueError):
            errors.append(f"Item {item_index + 1} modifier {modifier_index + 1}: Invalid price format")
        
        return errors