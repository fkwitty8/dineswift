import '../models/menu_item.dart';
import '../models/cart_item.dart';
import '../models/order.dart';
import '../models/booking.dart';

class ApiService {
  // ------------------ Menu ------------------
  /// Fetch menu items
  /// If tableId == 'table_7', returns a special menu
  /// Otherwise returns default menu
  Future<List<MenuItem>> fetchMenu([String? tableId]) async {
    await Future.delayed(const Duration(milliseconds: 500));

    if (tableId == 'table_7') {
      // Special menu for table_7
      return const [
        MenuItem(id: 'm10', name: 'Steak', price: 40.0, image: 'assets/images/food/pizza.png'),
        MenuItem(id: 'm11', name: 'Salad', price: 20.0, image: 'assets/images/food/burger.png'),
        MenuItem(id: 'm12', name: 'Wine', price: 30.0, image: 'assets/images/food/juice.png'),
      ];
    }

    // Default menu for all other tables or home
    return const [
      MenuItem(id: 'm1', name: 'Pizza', price: 25.0, image: 'assets/images/food/pizza.png'),
      MenuItem(id: 'm2', name: 'Burger', price: 15.0, image: 'assets/images/food/burger.png'),
      MenuItem(id: 'm3', name: 'Juice', price: 10.0, image: 'assets/images/food/juice.png'),
    ];
  }

  // ------------------ Cart ------------------
  static final List<CartItem> _cart = [];
  static List<CartItem> get cartItems => _cart;

  static void addToCart(MenuItem menuItem) {
    final existing = _cart.where((c) => c.item.id == menuItem.id).toList();
    if (existing.isNotEmpty) {
      existing.first.qty++;
    } else {
      _cart.add(CartItem(item: menuItem));
    }
  }

  static void removeFromCart(MenuItem menuItem) {
    _cart.removeWhere((c) => c.item.id == menuItem.id);
  }

  static void decrementItem(MenuItem menuItem) {
    final existing = _cart.where((c) => c.item.id == menuItem.id).toList();
    if (existing.isNotEmpty) {
      final first = existing.first;
      if (first.qty > 1) {
        first.qty--;
      } else {
        _cart.remove(first);
      }
    }
  }

  static double get cartTotal => _cart.fold(0.0, (s, c) => s + c.total);
  static void clearCart() => _cart.clear();

  // ------------------ Orders ------------------
  static final List<Order> _orders = [];
  static List<Order> get orders => _orders;

  static void placeOrder(String tableId) {
    final orderId = DateTime.now().millisecondsSinceEpoch.toString();
    final order = Order(
      tableId: tableId,
      items: _cart.map((c) => c.item).toList(),
      totalAmount: cartTotal,
      orderId: orderId,
    );
    _orders.add(order);
    clearCart();
  }

  // ------------------ Bookings ------------------
  static final List<Booking> _bookings = [];
  static List<Booking> get bookings => _bookings;

  static void addBooking(Booking booking) {
    _bookings.add(booking);
  }

  // ------------------ Feedback ------------------
  static final currentUser = {
    'name': 'Dorcus Nandy',
    'email': 'dineswiftuser@example.com',
    'membership': 'Gold Member',
    'points': 120,
  };

  static final List<Map<String, dynamic>> _feedbacks = [];

  /// Add feedback with rating (1-5), comment, user info, and timestamp
  static void addFeedback({required int rating, required String comment}) {
    final feedback = {
      'user': currentUser,
      'rating': rating,
      'comment': comment,
      'timestamp': DateTime.now(),
    };
    _feedbacks.add(feedback);
  }

  /// Get all feedbacks
  static List<Map<String, dynamic>> getAllFeedbacks() => _feedbacks;
}
