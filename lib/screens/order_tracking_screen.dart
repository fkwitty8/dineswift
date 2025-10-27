import 'package:flutter/material.dart';
import '../services/api_service.dart';

class OrderTrackingScreen extends StatelessWidget {
  const OrderTrackingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final orders = ApiService.orders;
    return Scaffold(
      appBar: AppBar(title: const Text('Order Tracking')),
      body: orders.isEmpty
          ? const Center(child: Text('No orders yet'))
          : ListView.builder(
        itemCount: orders.length,
        itemBuilder: (context, index) {
          final order = orders[index];
          return ListTile(
            title: Text('Order ${order.orderId}'),
            subtitle: Text('Table: ${order.tableId}\nItems: ${order.items.map((e) => e.name).join(', ')}'),
            trailing: Text('\$${order.totalAmount.toStringAsFixed(2)}'),
          );
        },
      ),
    );
  }
}
