import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'cart_screen.dart';
import 'qr_scan_screen.dart';

class MenuScreen extends StatefulWidget {
  final String? tableId; // Optional: null if opened from button

  const MenuScreen({super.key, this.tableId});

  @override
  State<MenuScreen> createState() => _MenuScreenState();
}

class _MenuScreenState extends State<MenuScreen> {
  late Future<List> menuFuture;
  late String displayTable;

  @override
  void initState() {
    super.initState();
    displayTable = widget.tableId ?? 'Menu';
    menuFuture = ApiService().fetchMenu(widget.tableId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(displayTable),
        actions: [
          IconButton(
            icon: const Icon(Icons.shopping_cart),
            onPressed: () {
              Navigator.push(context,
                  MaterialPageRoute(builder: (_) => const CartScreen()));
            },
          ),
          IconButton(
            icon: const Icon(Icons.qr_code_scanner),
            onPressed: () {
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => const QRScanScreen()),
              );
            },
          ),
        ],
      ),
      body: FutureBuilder(
        future: menuFuture,
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final menu = snapshot.data!;
          return ListView.builder(
            itemCount: menu.length,
            itemBuilder: (context, index) {
              final item = menu[index];
              return ListTile(
                leading: Image.asset(item.image, width: 50, height: 50),
                title: Text(item.name),
                subtitle: Text('\$${item.price.toStringAsFixed(2)}'),
                trailing: ElevatedButton(
                  child: const Text('Add'),
                  onPressed: () {
                    ApiService.addToCart(item);
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Added to cart')),
                    );
                  },
                ),
              );
            },
          );
        },
      ),
    );
  }
}
