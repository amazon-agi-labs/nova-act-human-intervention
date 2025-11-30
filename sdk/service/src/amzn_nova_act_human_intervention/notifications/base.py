from abc import ABC, abstractmethod
from enum import Enum
from typing import List

from amzn_nova_act_human_intervention_common import EmailContactInfo, SlackContactInfo, UseCase
from pydantic import BaseModel


class NotificationType(Enum):
    """Types of notifications that can be sent."""

    REQUEST_SENT = "request_sent"
    REQUEST_EXPIRED = "request_expired"
    REQUEST_TERMINATED = "request_terminated"
    REQUEST_APPROVED = "request_approved"  # Approval workflow only
    REQUEST_DENIED = "request_denied"  # Approval workflow only
    REQUEST_COMPLETED = "request_completed"  # UI Takeover workflow only


class NotificationData(BaseModel):
    """Pydantic model for notification data.

    Example:
        >>> from amzn_nova_act_human_intervention_common import EmailContactInfo, UseCase
        >>> data = NotificationData(
        ...     recipients=[EmailContactInfo(email="user@example.com")],
        ...     workflow_run_id="550e8400-e29b-41d4-a716-446655440000",
        ...     session_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ...     act_id="abcdef12-3456-7890-abcd-ef1234567890",
        ...     use_case=UseCase.UI_TAKEOVER,
        ...     notification_type=NotificationType.REQUEST_SENT,
        ...     message="Please complete the reCAPTCHA",
        ...     temporary_link="https://example.com/spa/12345",
        ...     expiration_time_utc="2025-11-09 18:00:00 UTC"
        ... )
    """

    # Common fields (always present)
    recipients: List[EmailContactInfo | SlackContactInfo]
    workflow_run_id: str
    session_id: str
    act_id: str
    use_case: UseCase
    notification_type: NotificationType
    message: str

    # Optional fields (depend on notification type)
    temporary_link: str | None = None
    expiration_time_utc: str | None = None

    # Threading support - for sending messages in the same conversation thread
    slack_thread_identifier: str | None = None


class BaseNotifier(ABC):
    @abstractmethod
    def send(self, data: NotificationData) -> bool: ...
