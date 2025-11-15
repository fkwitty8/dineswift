import 'package:flutter_test/flutter_test.dart';
import 'package:dineswiftapp/main.dart'; // ✅ Correct import

void main() {
  testWidgets('App loads and shows DineSwift title', (WidgetTester tester) async {
    // Build the app
    await tester.pumpWidget(const DineSwiftApp());

    // Verify the app title text appears
    expect(find.text('DineSwift'), findsOneWidget);

    // Verify that the "Scan QR Code" button is visible
    expect(find.text('Scan QR Code'), findsOneWidget);

    // Verify that the "Book a Table" button is visible
    expect(find.text('Book a Table'), findsOneWidget);
  });
}
