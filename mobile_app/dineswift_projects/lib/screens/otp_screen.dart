import 'package:flutter/material.dart';

class OTPScreen extends StatefulWidget {
  const OTPScreen({super.key});

  @override
  State<OTPScreen> createState() => _OTPScreenState();
}

class _OTPScreenState extends State<OTPScreen> {
  String? _otpCode;
  DateTime? _otpExpiry;
  Duration _remainingTime = Duration.zero;
  bool _initialized = false;

  @override
  void initState() {
    super.initState();
    // Logic is moved to didChangeDependencies to safely access ModalRoute
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialized) {
      final args = ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
      _otpCode = args?['otpCode'] ?? '123456';
      _otpExpiry = DateTime.parse(args?['otpExpiry'] ?? DateTime.now().add(const Duration(minutes: 5)).toIso8601String());
      _remainingTime = _otpExpiry!.difference(DateTime.now());

      if (_remainingTime.isNegative) {
        _remainingTime = Duration.zero;
      }

      _startTimer();
      _initialized = true;
    }
  }

  void _startTimer() {
    Future.delayed(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() {
          _remainingTime = _remainingTime > const Duration(seconds: 1)
              ? _remainingTime - const Duration(seconds: 1)
              : Duration.zero;
        });

        if (_remainingTime.inSeconds > 0) {
          _startTimer();
        }
      }
    });
  }

  void _refreshOTP() {
    if (mounted) {
      setState(() {
        _otpCode = (DateTime.now().millisecond % 1000000).toString().padLeft(6, '0');
        _otpExpiry = DateTime.now().add(const Duration(minutes: 5));
        _remainingTime = const Duration(minutes: 5);
      });
      _startTimer();
    }
  }

  void _copyToClipboard() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('OTP copied to clipboard')),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_initialized || _otpCode == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    final minutes = _remainingTime.inMinutes;
    final seconds = _remainingTime.inSeconds % 60;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Your OTP Code'),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.qr_code,
              size: 80,
              color: Colors.deepPurple,
            ),
            const SizedBox(height: 32),
            const Text(
              'Show this code to staff to collect your order',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                border: Border.all(color: Colors.deepPurple),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                children: [
                  Text(
                    _otpCode!,
                    style: const TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 4,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Expires in: ${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}',
                    style: TextStyle(
                      color: _remainingTime.inMinutes < 1 ? Colors.red : Colors.grey,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ElevatedButton.icon(
                  onPressed: _copyToClipboard,
                  icon: const Icon(Icons.copy),
                  label: const Text('Copy Code'),
                ),
                const SizedBox(width: 16),
                ElevatedButton.icon(
                  onPressed: _remainingTime.inSeconds <= 0 ? _refreshOTP : null,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh OTP'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () {
                Navigator.pushNamed(context, '/order_tracking');
              },
              child: const Text('Track Order Status'),
            ),
          ],
        ),
      ),
    );
  }
}
