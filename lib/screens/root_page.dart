import 'package:flutter/material.dart';
import 'bottom_nav_root.dart';

class RootPage extends StatelessWidget {
  const RootPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: BottomNavRoot(),
    );
  }
}
