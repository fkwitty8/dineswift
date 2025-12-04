# apps/payment/exceptions.py

class WalletError(Exception):
    """Base exception for all wallet errors."""
    pass

class InsufficientFundsError(WalletError):
    """Raised when available balance is too low for a deduction or authorization."""
    pass

class InactiveWalletError(WalletError):
    """Raised when an operation is attempted on a suspended or closed wallet."""
    pass

class InvalidPendingCaptureError(WalletError):
    """Raised when trying to capture or release more than is currently pending."""
    pass

class InvalidAmountError(WalletError):
    """Raised when an invalid amount (e.g., zero or negative) is provided for an operation."""
    pass

class RefundError(WalletError):
    """Raised when trying to refund more 0 or negative amount."""
    pass
class MaxBalanceExceededError(WalletError):
    """Raised when adding funds would exceed the wallet's maximum balance."""
    pass