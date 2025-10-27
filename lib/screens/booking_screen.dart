import 'package:flutter/material.dart';
import '../models/booking.dart';
import '../services/api_service.dart';

class BookingScreen extends StatefulWidget {
  const BookingScreen({super.key});

  @override
  State<BookingScreen> createState() => _BookingScreenState();
}

class _BookingScreenState extends State<BookingScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _tableController = TextEditingController();
  final _dateController = TextEditingController();
  final _timeController = TextEditingController();
  final _guestsController = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Book a Table')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          key: _formKey,
          child: ListView(
            children: [
              TextFormField(
                controller: _nameController,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (v) => v!.isEmpty ? 'Enter name' : null,
              ),
              TextFormField(
                controller: _tableController,
                decoration: const InputDecoration(labelText: 'Table Number'),
                validator: (v) => v!.isEmpty ? 'Enter table number' : null,
              ),
              TextFormField(
                controller: _dateController,
                decoration: const InputDecoration(labelText: 'Date'),
                validator: (v) => v!.isEmpty ? 'Enter date' : null,
              ),
              TextFormField(
                controller: _timeController,
                decoration: const InputDecoration(labelText: 'Time'),
                validator: (v) => v!.isEmpty ? 'Enter time' : null,
              ),
              TextFormField(
                controller: _guestsController,
                decoration: const InputDecoration(labelText: 'Number of Guests'),
                keyboardType: TextInputType.number,
                validator: (v) => v!.isEmpty ? 'Enter guests' : null,
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: () {
                  if (_formKey.currentState!.validate()) {
                    final booking = Booking(
                      name: _nameController.text,
                      tableNumber: _tableController.text,
                      date: _dateController.text,
                      time: _timeController.text,
                      guests: int.parse(_guestsController.text),
                    );
                    ApiService.addBooking(booking);
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Booking Confirmed')),
                    );
                  }
                },
                child: const Text('Confirm Booking'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
