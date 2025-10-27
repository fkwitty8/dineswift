import 'package:flutter/material.dart';
import 'feedback_screen.dart';
import 'chat_screen.dart';
import 'loyalty_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Profile'),
        backgroundColor: Colors.deepOrangeAccent,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          children: [
            const CircleAvatar(
              radius: 50,
              backgroundColor: Colors.deepOrangeAccent,
              child: Icon(Icons.person, size: 60, color: Colors.white),
            ),
            const SizedBox(height: 15),
            const Text(
              'Dorcus Nandy',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),
            const Text('dineswiftuser@example.com'),
            const SizedBox(height: 20),
            Card(
              elevation: 2,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              child: ListTile(
                leading: const Icon(Icons.star, color: Colors.amber),
                title: const Text('Gold Member'),
                subtitle: const Text('Loyalty Points: 120'),
                trailing: TextButton(
                  onPressed: () {
                    Navigator.push(context, MaterialPageRoute(builder: (_) => const LoyaltyScreen()));
                  },
                  child: const Text('View'),
                ),
              ),
            ),
            const SizedBox(height: 20),
            ListTile(
              leading: const Icon(Icons.chat, color: Colors.deepOrangeAccent),
              title: const Text('Chat with Waiter'),
              onTap: () {
                Navigator.push(context, MaterialPageRoute(builder: (_) => const ChatScreen()));
              },
            ),
            const Divider(),
            ListTile(
              leading: const Icon(Icons.feedback, color: Colors.green),
              title: const Text('Give Feedback'),
              onTap: () {
                Navigator.push(context, MaterialPageRoute(builder: (_) => const FeedbackScreen()));
              },
            ),
          ],
        ),
      ),
    );
  }
}
