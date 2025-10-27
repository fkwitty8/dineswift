import 'package:flutter/material.dart';
import 'screens/root_page.dart';
import 'services/api_service.dart';
import 'models/menu_item.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Optionally, preload menu items
  await ApiService().fetchMenu();

  runApp(const DineSwiftApp());
}

class DineSwiftApp extends StatelessWidget {
  const DineSwiftApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DineSwift',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primarySwatch: Colors.orange,
        brightness: Brightness.light,
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.orange,
          foregroundColor: Colors.white,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.orange,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            textStyle: const TextStyle(fontSize: 18),
          ),
        ),
      ),
      home: const RootPage(),
    );
  }
}
