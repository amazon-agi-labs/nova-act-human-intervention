"""Custom exceptions for notification delivery."""


class NotificationDeliveryError(Exception):
    """Exception raised when notification delivery fails for one or more channels.

    This exception is raised by the NotificationFactory when it fails to deliver
    notifications through any of the configured channels (Email, Slack, etc.).
    It contains information about which channels failed and the error details.

    Attributes:
        message: Human-readable error message describing the failure
        failed_channels: List of channel-specific error messages
    """

    def __init__(self, message: str, failed_channels: list[str]) -> None:
        """Initialize NotificationDeliveryError.

        Args:
            message: Human-readable error message
            failed_channels: List of strings describing channel-specific failures
        """
        super().__init__(message)
        self.failed_channels = failed_channels
