import 'package:flutter/material.dart';
import '../services/api_service.dart';

class FeedbackHistoryScreen extends StatelessWidget {
  const FeedbackHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final feedbacks = ApiService.getAllFeedbacks().reversed.toList(); // newest first

    return Scaffold(
      appBar: AppBar(
        title: const Text('Feedback History'),
        backgroundColor: Colors.deepOrange, // DineSwift theme color
      ),
      body: feedbacks.isEmpty
          ? const Center(
        child: Text(
          'No feedback submitted yet.',
          style: TextStyle(fontSize: 16),
        ),
      )
          : ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: feedbacks.length,
        itemBuilder: (context, index) {
          final fb = feedbacks[index];
          final user = fb['user'];
          final rating = fb['rating'];
          final comment = fb['comment'];
          final timestamp = fb['timestamp'] as DateTime;

          return Card(
            margin: const EdgeInsets.symmetric(vertical: 6),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            elevation: 2,
            child: ListTile(
              contentPadding: const EdgeInsets.all(12),
              title: Text(
                '${user['name']} (${user['membership']})',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 4),
                  Row(
                    children: List.generate(
                      5,
                          (i) => Icon(
                        i < rating ? Icons.star : Icons.star_border,
                        color: Colors.amber,
                        size: 20,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(comment),
                  const SizedBox(height: 6),
                  Text(
                    '${timestamp.day}/${timestamp.month}/${timestamp.year} ${timestamp.hour}:${timestamp.minute.toString().padLeft(2,'0')}',
                    style: const TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
