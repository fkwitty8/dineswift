import 'package:flutter/material.dart';
import 'home_screen_ui.dart';
import 'cart_screen.dart';
import 'profile_screen.dart';
import 'booking_screen.dart';

class BottomNavRoot extends StatefulWidget {
  const BottomNavRoot({super.key});

  @override
  State<BottomNavRoot> createState() => _BottomNavRootState();
}

class _BottomNavRootState extends State<BottomNavRoot> {
  int _currentIndex = 0;
  final List<Widget> _pages = const [
    HomeScreen(),
    CartScreen(),
    BookingScreen(),
    ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        selectedItemColor: Colors.orange,
        unselectedItemColor: Colors.grey,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.shopping_cart), label: 'Cart'),
          BottomNavigationBarItem(icon: Icon(Icons.book_online), label: 'Booking'),
          BottomNavigationBarItem(icon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
