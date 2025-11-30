"""Request models for Nova Act Human Intervention."""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from amzn_nova_act_human_intervention_common.models.common_models import NotificationRecipient
from amzn_nova_act_human_intervention_common.models.intervention_models import BrowserSessionContext


class ApprovalAction(str, Enum):
    """Approval action types.

    Attributes
    ----------
    APPROVE : str
        Positive approval action
    DENY : str
        Negative denial action
    """

    APPROVE = "APPROVE"
    DENY = "DENY"


class ApprovalOption(BaseModel):
    """Approval option with display label and action type.

    Attributes
    ----------
    label : str
        Display text for the button (e.g., "Yes", "Approve", "Continue")
    action : ApprovalAction
        Normalized action type (APPROVE or DENY)

    Examples
    --------
    Approval option::

        {
            "label": "Yes, Continue",
            "action": "APPROVE"
        }

    Denial option::

        {
            "label": "Cancel",
            "action": "DENY"
        }
    """

    label: str
    action: ApprovalAction


class HITLRequest(BaseModel):
    """Base request for Human-in-the-Loop interventions.

    Attributes
    ----------
    notification_recipients : List[NotificationRecipient]
        List of recipients for notifications (email or Slack)
    timeout : int, default=86400
        Timeout in seconds (default: 24 hours)

    Examples
    --------
    Basic HITL request::

        {
            "notification_recipients": [
                {
                    "contact_info": "user@example.com",
                    "channel": "Email"
                }
            ],
            "timeout": 86400
        }
    """

    notification_recipients: List[NotificationRecipient]
    timeout: int = Field(default=24 * 60 * 60)


class UITakeoverRequest(HITLRequest):
    """Request for UI takeover intervention.

    Extends HITLRequest with UI takeover-specific fields for browser session control.

    Attributes
    ----------
    message : str
        Description of required human interaction
    browser_session : BrowserSessionContext
        Browser session context for remote control

    Examples
    --------
    UI Takeover request::

        {
            "notification_recipients": [
                {
                    "contact_info": "user@example.com",
                    "channel": "Email"
                }
            ],
            "timeout": 86400,
            "message": "Please complete the form submission on the checkout page",
            "browser_session": {
                "session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"
            }
        }
    """

    message: str
    browser_session: BrowserSessionContext


class ApprovalRequest(HITLRequest):
    """Request for approval intervention.

    Extends HITLRequest with approval-specific fields for presenting a question
    with options and visual context to a human approver.

    Attributes
    ----------
    question : str
        Question to ask for approval
    options : List[ApprovalOption]
        Available response options with labels and actions.
        Defaults to [Approve, Cancel] if not provided.
    most_recent_screenshot : str
        Base64-encoded data URL of the screenshot (PNG or JPEG).
        Input is a data URL that the client will upload to S3 and convert to presigned URL.

    Examples
    --------
    Approval request::

        {
            "notification_recipients": [
                {
                    "contact_info": "user@example.com",
                    "channel": "Email"
                }
            ],
            "timeout": 86400,
            "question": "Do you approve this purchase order for $1,500?",
            "options": [
                {"label": "Approve", "action": "APPROVE"},
                {"label": "Cancel", "action": "DENY"}
            ],
            "most_recent_screenshot": "data:image/png;base64,iVBORw0KGgoAAAANSUh..."
        }
    """

    question: str
    options: List[ApprovalOption] = Field(
        default_factory=lambda: [
            ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
            ApprovalOption(label="Cancel", action=ApprovalAction.DENY),
        ]
    )
    most_recent_screenshot: str
