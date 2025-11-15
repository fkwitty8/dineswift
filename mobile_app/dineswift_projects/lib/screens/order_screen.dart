import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'payment_screen.dart';

class OrderScreen extends StatelessWidget {
  const OrderScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final cartItems = ApiService.cartItems;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Order Summary'),
        backgroundColor: Colors.deepOrangeAccent,
      ),
      body: cartItems.isEmpty
          ? const Center(
        child: Text(
          'Your cart is empty',
          style: TextStyle(fontSize: 18),
        ),
      )
          : ListView.builder(
        itemCount: cartItems.length,
        itemBuilder: (context, index) {
          final c = cartItems[index];
          return ListTile(
            leading: Image.asset(
              c.item.image,
              width: 50,
              height: 50,
              fit: BoxFit.cover,
            ),
            title: Text(c.item.name),
            subtitle: Text(
              '${c.qty} x \$${c.item.price.toStringAsFixed(2)} = \$${c.total.toStringAsFixed(2)}',
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
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) =>
                    PaymentScreen(amount: ApiService.cartTotal),
              ),
            );
          },
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.deepOrangeAccent,
            minimumSize: const Size(double.infinity, 50),
          ),
          child: Text(
            cartItems.isEmpty
                ? 'Cart is empty'
                : 'Proceed to Pay (\$${ApiService.cartTotal.toStringAsFixed(2)})',
            style: const TextStyle(fontSize: 16, color: Colors.white),
          ),
        ),
      ),
    );
  }
}
