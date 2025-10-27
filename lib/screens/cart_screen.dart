import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'order_confirmation_screen.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({super.key});

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  @override
  Widget build(BuildContext context) {
    final cartItems = ApiService.cartItems;

    return Scaffold(
      appBar: AppBar(title: const Text('Cart')),
      body: cartItems.isEmpty
          ? const Center(child: Text('Cart is empty'))
          : ListView.builder(
        itemCount: cartItems.length,
        itemBuilder: (context, index) {
          final c = cartItems[index];
          return ListTile(
            leading: Image.asset(c.item.image, width: 50, height: 50),
            title: Text(c.item.name),
            subtitle: Text('${c.qty} x \$${c.item.price} = \$${c.total}'),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                    icon: const Icon(Icons.remove),
                    onPressed: () {
                      setState(() {
                        ApiService.decrementItem(c.item);
                      });
                    }),
                IconButton(
                    icon: const Icon(Icons.add),
                    onPressed: () {
                      setState(() {
                        ApiService.addToCart(c.item);
                      });
                    }),
              ],
            ),
          );
        },
      ),
      bottomNavigationBar: Container(
        padding: const EdgeInsets.all(16),
        height: 80,
        child: ElevatedButton(
          onPressed: cartItems.isEmpty
              ? null
              : () {
            // For simplicity, we assign tableId 'table_1' here
            ApiService.placeOrder('table_1');
            Navigator.push(
              context,
              MaterialPageRoute(
                  builder: (_) => const OrderConfirmationScreen()),
            );
          },
          child: Text('Checkout (\$${ApiService.cartTotal.toStringAsFixed(2)})'),
        ),
      ),
    );
  }
}
