import 'package:flutter/material.dart';
import 'package:qr_code_scanner_plus/qr_code_scanner_plus.dart';
import 'menu_screen.dart';

class QRScanScreen extends StatefulWidget {
  const QRScanScreen({super.key});

  @override
  State<QRScanScreen> createState() => _QRScanScreenState();
}

class _QRScanScreenState extends State<QRScanScreen> {
  final GlobalKey qrKey = GlobalKey(debugLabel: 'QR');
  QRViewController? controller;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Table QR')),
      body: QRView(
        key: qrKey,
        onQRViewCreated: _onQRViewCreated,
      ),
    );
  }

  void _onQRViewCreated(QRViewController controller) {
    this.controller = controller;

    controller.scannedDataStream.listen((scanData) {
      final data = scanData.code ?? '';

      // Stop camera after first scan
      controller.pauseCamera();

      _handleScannedData(data);
    });
  }

  void _handleScannedData(String data) {
    // ✅ Detect table ID dynamically
    // Works for any QR containing "table_1", "table_2", ..., "table_X"
    String tableId = '';
    final tableRegex = RegExp(r'table_\d+');

    final match = tableRegex.firstMatch(data);
    if (match != null) {
      tableId = match.group(0)!; // "table_7", "table_12", etc.
    } else {
      tableId = 'unknown_table'; // fallback if QR doesn't have table info
    }

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => MenuScreen(tableId: tableId)),
    );
  }

  @override
  void dispose() {
    controller?.dispose();
    super.dispose();
  }
}
