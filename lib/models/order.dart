import 'menu_item.dart';

class Order {
  final String tableId;
  final List<MenuItem> items;
  final double totalAmount;
  final String orderId;

  Order({
    required this.tableId,
    required this.items,
    required this.totalAmount,
    required this.orderId,
  });
}
