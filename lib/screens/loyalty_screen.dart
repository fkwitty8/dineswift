import 'package:flutter/material.dart';
import '../services/api_service.dart';

class LoyaltyScreen extends StatelessWidget {
  const LoyaltyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = ApiService.currentUser;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Loyalty Program'),
        backgroundColor: Colors.deepOrangeAccent,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const Icon(Icons.star, color: Colors.amber, size: 100),
            const SizedBox(height: 10),
            Text('${user['name']}', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 5),
            Text('Level: ${user['membership']}', style: const TextStyle(fontSize: 18)),
            const SizedBox(height: 15),
            Text('Points: ${user['points']}', style: const TextStyle(fontSize: 18, color: Colors.green)),
            const SizedBox(height: 30),
            const Text(
              'Earn points on every order you make. Redeem them for free meals, drinks, or discounts.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, color: Colors.black54),
            ),
          ],
        ),
      ),
    );
  }
}
