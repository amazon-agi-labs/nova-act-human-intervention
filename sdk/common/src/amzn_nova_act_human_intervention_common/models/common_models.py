"""Common models shared across multiple modules."""

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UseCase(str, Enum):
    """Types of human intervention use cases.

    Attributes
    ----------
    APPROVAL : str
        Approval workflow requiring human decision on a yes/no question
    UI_TAKEOVER : str
        UI Takeover workflow requiring human interaction with a browser session
    """

    APPROVAL = "Approval"
    UI_TAKEOVER = "UITakeover"


class NotificationChannel(str, Enum):
    """Types of notification channels.

    Attributes
    ----------
    EMAIL : str
        Email notification channel
    SLACK : str
        Slack notification channel
    """

    EMAIL = "Email"
    SLACK = "Slack"


class SlackTargetType(str, Enum):
    """Types of Slack notification targets.

    Attributes
    ----------
    USER : str
        Individual Slack user (e.g., @username or user ID)
    USERGROUP : str
        Slack user group (e.g., <!subteam^S12345>)
    """

    USER = "user"
    USERGROUP = "usergroup"


class ContactInfo(BaseModel):
    """Base class for contact information.

    Attributes
    ----------
    type : str
        The type of contact information (email or slack)
    """

    type: str


class EmailContactInfo(ContactInfo):
    """Email contact information.

    Attributes
    ----------
    type : Literal["email"]
        Contact type identifier (always "email"). Used as Pydantic discriminator
        for efficient deserialization of NotificationRecipient union types.
    to_email_address : str
        Recipient's email address (must be valid email format)
    from_email_address : str
        Sender's email address (like AWS SES From field, must be valid email format)

    Examples
    --------
    Email notification::

        {
            "type": "email",
            "to_email_address": "user@example.com",
            "from_email_address": "noreply@example.com"
        }
    """

    type: Literal["email"] = "email"  # Discriminator for Pydantic union deserialization
    to_email_address: str
    from_email_address: str

    @field_validator("to_email_address", "from_email_address")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        """Validate email address format.

        Args:
            value: Email address to validate

        Returns:
            Validated email address

        Raises:
            ValueError: If email format is invalid
        """
        # Check for empty string first
        if not value or not value.strip():
            raise ValueError(f"Invalid email address format: {value}")

        # Basic email validation regex
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, value):
            raise ValueError(f"Invalid email address format: {value}")
        return value


class SlackContactInfo(ContactInfo):
    """Slack contact information.

    Attributes
    ----------
    type : Literal["slack"]
        Contact type identifier (always "slack"). Used as Pydantic discriminator
        for efficient deserialization of NotificationRecipient union types.
    channel : str
        Slack channel name (e.g., "#general") or channel ID (e.g., "C123456")
    target : str
        For users: username with @ (e.g., "@username") or user ID (e.g., "U12345")
        For usergroups: just the group ID (e.g., "S12345")
        Note: The Slack mention format (e.g., "<!subteam^S12345>") is handled automatically
    target_type : SlackTargetType
        Type of Slack target (user or usergroup)

    Examples
    --------
    Slack user with username::

        {
            "type": "slack",
            "channel": "#general",
            "target": "@username",
            "target_type": "user"
        }

    Slack user with user ID::

        {
            "type": "slack",
            "channel": "#general",
            "target": "U12345",
            "target_type": "user"
        }

    Slack user group::

        {
            "type": "slack",
            "channel": "#incident-response",
            "target": "S12345",
            "target_type": "usergroup"
        }

    Notes
    -----
    When target_type is "usergroup", the target should be just the group ID (e.g., "S12345").
    The system will automatically format it as "<!subteam^S12345>" for Slack API calls.
    """

    type: Literal["slack"] = "slack"  # Discriminator for Pydantic union deserialization
    channel: str
    target: str
    target_type: SlackTargetType = SlackTargetType.USER


class NotificationRecipient(BaseModel):
    """Notification recipient model.

    Attributes
    ----------
    contact_info : EmailContactInfo | SlackContactInfo
        Contact information structured by notification type

    Examples
    --------
    Email recipient::

        {
            "contact_info": {
                "type": "email",
                "to_email_address": "user@example.com",
                "from_email_address": "noreply@example.com"
            }
        }

    Slack user recipient::

        {
            "contact_info": {
                "type": "slack",
                "channel": "#general",
                "target": "@username",
                "target_type": "user"
            }
        }

    Slack user group recipient::

        {
            "contact_info": {
                "type": "slack",
                "channel": "#incident-response",
                "target": "S12345",
                "target_type": "usergroup"
            }
        }
    """

    contact_info: EmailContactInfo | SlackContactInfo = Field(discriminator="type")

    @property
    def channel(self) -> NotificationChannel:
        """Derive notification channel from contact_info type.

        Returns
        -------
        NotificationChannel
            EMAIL for EmailContactInfo, SLACK for SlackContactInfo
        """
        if isinstance(self.contact_info, EmailContactInfo):
            return NotificationChannel.EMAIL
        return NotificationChannel.SLACK
