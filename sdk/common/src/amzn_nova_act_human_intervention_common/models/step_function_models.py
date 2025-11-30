"""Step function models for Nova Act Human Intervention."""

from typing import Any, Dict, List, Union

from pydantic import BaseModel, field_validator

from amzn_nova_act_human_intervention_common.models.common_models import NotificationRecipient, UseCase
from amzn_nova_act_human_intervention_common.models.intervention_models import (
    BrowserSessionContext,
)
from amzn_nova_act_human_intervention_common.models.request_models import ApprovalOption


class StepFunctionInput(BaseModel):
    """Base input for Step Function execution.

    Base class for all intervention workflow inputs. Provides common fields
    and validation for workflow identification and notification.

    Attributes
    ----------
    workflow_run_id : str
        Unique identifier for the workflow run
    session_id : str
        Session identifier
    act_id : str
        Act identifier
    event_id : str
        Event identifier
    type : UseCase
        Use case type (UI_TAKEOVER or APPROVAL)
    timeout : int
        Timeout in seconds
    notification_recipients : List[NotificationRecipient]
        List of notification recipients (1-3 recipients)

    Examples
    --------
    Basic step function input::

        {
            "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            "session_id": "87654321-4321-4321-4321-210987654321",
            "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            "event_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "type": "UITakeover",
            "timeout": 86400,
            "notification_recipients": [
                {
                    "contact_info": "user@example.com",
                    "channel": "Email"
                }
            ]
        }
    """

    workflow_run_id: str
    session_id: str
    act_id: str
    event_id: str
    type: UseCase
    timeout: int
    notification_recipients: List[NotificationRecipient]

    @classmethod
    @field_validator("notification_recipients")
    def validate_notification_recipients(cls, v: List[NotificationRecipient]) -> List[NotificationRecipient]:
        if len(v) < 1:
            raise ValueError("Please provide at least one notification recipient.")
        if len(v) > 3:
            raise ValueError(
                "Too many notification recipients.Please create an Email list or a dedicated Slack channel(s)."
            )
        return v

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> Union["UITakeoverStepFunctionInput", "ApprovalStepFunctionInput"]:
        """Convert JSON payload to appropriate StepFunctionInput subclass.

        Parameters
        ----------
        payload : Dict[str, Any]
            Dictionary containing the payload data with 'type' field

        Returns
        -------
        UITakeoverStepFunctionInput or ApprovalStepFunctionInput
            Appropriate StepFunctionInput subclass instance based on use case type

        Raises
        ------
        ValueError
            If use case type is not supported (not UITakeover or Approval)

        Examples
        --------
        Convert UITakeover payload to typed object::

            >>> payload = {
            ...     "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            ...     "session_id": "87654321-4321-4321-4321-210987654321",
            ...     "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            ...     "event_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            ...     "type": "UITakeover",
            ...     "timeout": 86400,
            ...     "notification_recipients": [
            ...         {"contact_info": {"type": "email", "to_email_address": "user@example.com",
            ...          "from_email_address": "noreply@example.com"}}
            ...     ],
            ...     "message": "Please complete the form",
            ...     "remote_browser": {"session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"}
            ... }
            >>> step_input = StepFunctionInput.from_payload(payload)
            >>> type(step_input).__name__
            'UITakeoverStepFunctionInput'
            >>> step_input.message
            'Please complete the form'

        Convert Approval payload to typed object::

            >>> payload = {
            ...     "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            ...     "session_id": "87654321-4321-4321-4321-210987654321",
            ...     "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            ...     "event_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            ...     "type": "Approval",
            ...     "timeout": 86400,
            ...     "notification_recipients": [
            ...         {"contact_info": {"type": "email", "to_email_address": "user@example.com",
            ...          "from_email_address": "noreply@example.com"}}
            ...     ],
            ...     "query": "Approve this purchase?",
            ...     "options": [{"label": "Approve", "action": "APPROVE"}],
            ...     "most_recent_screenshot": "https://s3.amazonaws.com/..."
            ... }
            >>> step_input = StepFunctionInput.from_payload(payload)
            >>> type(step_input).__name__
            'ApprovalStepFunctionInput'
            >>> step_input.query
            'Approve this purchase?'
        """
        use_case: UseCase = UseCase(payload["type"])
        if use_case == UseCase.UI_TAKEOVER:
            return UITakeoverStepFunctionInput(**payload)
        elif use_case == UseCase.APPROVAL:
            return ApprovalStepFunctionInput(**payload)
        else:
            raise ValueError(f"Unsupported use case: {use_case}")


class UITakeoverStepFunctionInput(StepFunctionInput):
    """Step function input for UI takeover intervention.

    Extends StepFunctionInput with UI takeover-specific fields for browser
    session control and human interaction messaging.

    Attributes
    ----------
    message : str
        Message describing what human input is needed
    remote_browser : BrowserSessionContext
        Remote browser session context with session ID

    Examples
    --------
    UI Takeover step function input::

        {
            "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            "session_id": "87654321-4321-4321-4321-210987654321",
            "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            "event_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "type": "UITakeover",
            "timeout": 86400,
            "notification_recipients": [
                {
                    "contact_info": "user@example.com",
                    "channel": "Email"
                }
            ],
            "message": "Please complete the form submission on the checkout page",
            "remote_browser": {
                "session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"
            }
        }
    """

    message: str
    remote_browser: BrowserSessionContext


class ApprovalStepFunctionInput(StepFunctionInput):
    """Step function input for approval intervention.

    Extends StepFunctionInput with approval-specific fields for presenting
    a question with options and context to a human approver.

    Attributes
    ----------
    query : str
        Question to ask for approval
    options : List[ApprovalOption]
        Available response options with labels and actions (APPROVE/DENY)
    most_recent_screenshot : str
        Presigned S3 URL to the screenshot (valid for 1 hour).
        Screenshot is uploaded to S3 by the client and deleted after SPA generation.

    Examples
    --------
    Approval step function input::

        {
            "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            "session_id": "87654321-4321-4321-4321-210987654321",
            "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            "event_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "type": "Approval",
            "timeout": 86400,
            "notification_recipients": [
                {
                    "contact_info": "user@example.com",
                    "channel": "Email"
                }
            ],
            "query": "Do you approve this purchase order for $1,500?",
            "options": [
                {"label": "Approve", "action": "APPROVE"},
                {"label": "Cancel", "action": "DENY"}
            ],
            "most_recent_screenshot": "https://s3.amazonaws.com/bucket/path/screenshot.png?..."
        }
    """

    query: str
    options: List[ApprovalOption]
    most_recent_screenshot: str
