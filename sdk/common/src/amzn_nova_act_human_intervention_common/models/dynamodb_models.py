"""DynamoDB models for Nova Act Human Intervention."""

import time
from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from amzn_nova_act_human_intervention_common.models.common_models import NotificationRecipient, UseCase
from amzn_nova_act_human_intervention_common.models.request_models import ApprovalOption
from amzn_nova_act_human_intervention_common.models.step_function_models import (
    ApprovalStepFunctionInput,
    UITakeoverStepFunctionInput,
)
from amzn_nova_act_human_intervention_common.models.type_definitions import GenericDict, InterventionRequest


class ExecutionStatus(str, Enum):
    """Human intervention workflow execution status states.

    Attributes
    ----------
    IN_PROGRESS : str
        Workflow is actively executing
    PENDING_HUMAN_INPUT : str
        Workflow is waiting for human input
    COMPLETED : str
        Workflow completed successfully
    FAILED : str
        Workflow failed due to an error
    TERMINATED : str
        Workflow was manually terminated
    """

    IN_PROGRESS = "IN_PROGRESS"
    PENDING_HUMAN_INPUT = "PENDING_HUMAN_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"

    def is_terminal(self) -> bool:
        """Check if this status represents a terminal/completed state.

        Terminal states indicate the workflow has finished and will not
        process further. Used for determining if task polling should stop.

        Returns
        -------
        bool
            True if status is COMPLETED, FAILED, or TERMINATED
        """
        return self in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TERMINATED,
        }

    def has_user_action(self) -> bool:
        """Check if this status indicates user has already taken action.

        User action statuses mean the user has explicitly interacted with
        the workflow (completed it or terminated it). Used to determine
        if expiration notifications should be skipped.

        Returns
        -------
        bool
            True if status is COMPLETED or TERMINATED
        """
        return self in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.TERMINATED,
        }


class ErrorCode(str, Enum):
    """Error codes for failed workflow executions.

    Attributes
    ----------
    TIMEOUT : str
        Session expired before completion
    BROWSER_SESSION_TERMINATED : str
        Remote browser session was terminated
    PAGE_GENERATION_FAILED : str
        Failed to generate the user interface
    NOTIFICATION_FAILED : str
        Failed to send notifications
    SYSTEM_ERROR : str
        Generic system failure
    EXECUTION_FAILED : str
        Step Functions execution failed
    """

    TIMEOUT = "TIMEOUT"
    BROWSER_SESSION_TERMINATED = "BROWSER_SESSION_TERMINATED"
    PAGE_GENERATION_FAILED = "PAGE_GENERATION_FAILED"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class ErrorDetails(BaseModel):
    """Error details for failed workflow executions.

    Attributes
    ----------
    code : str
        Machine-readable error code (e.g., TIMEOUT, PAGE_GENERATION_FAILED)
    message : str
        Human-readable error message for display to users

    Examples
    --------
    Error details for timeout::

        {
            "code": "TIMEOUT",
            "message": "This request has expired. The time limit for completing this task has been exceeded."
        }

    Error details for browser termination::

        {
            "code": "BROWSER_SESSION_TERMINATED",
            "message": "The browser session has been terminated. The remote browser is no longer available."
        }
    """

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")

    @classmethod
    def from_error_code(cls, error_code: ErrorCode) -> "ErrorDetails":
        """Create ErrorDetails from an ErrorCode enum.

        Parameters
        ----------
        error_code : ErrorCode
            The error code enum value

        Returns
        -------
        ErrorDetails
            Error details with appropriate message for the error code
        """
        error_messages = {
            ErrorCode.TIMEOUT: "This request has expired. The time limit for completing this task has been exceeded.",
            ErrorCode.BROWSER_SESSION_TERMINATED: (
                "The browser session has been terminated. The remote browser is no longer available."
            ),
            ErrorCode.PAGE_GENERATION_FAILED: (
                "Failed to generate the user interface. Please contact your administrator."
            ),
            ErrorCode.NOTIFICATION_FAILED: (
                "Failed to send notifications. The request may not have been delivered to the intended recipients."
            ),
            ErrorCode.SYSTEM_ERROR: (
                "A system error occurred while processing this request. Please contact your administrator."
            ),
            ErrorCode.EXECUTION_FAILED: (
                "The workflow execution failed. Please contact your administrator for more information."
            ),
        }
        return cls(code=error_code.value, message=error_messages[error_code])


class ConnectionItem(BaseModel):
    """WebSocket connection item for DynamoDB storage.

    Represents a WebSocket connection with automatic TTL for cleanup.
    Used to track active connections in DynamoDB with expiration.

    Attributes
    ----------
    connectionId : str
        Unique WebSocket connection identifier from API Gateway
    timestamp : int
        Unix timestamp when connection was established
    ttl : int
        Unix timestamp when connection should expire (for DynamoDB TTL)

    Examples
    --------
    >>> item = ConnectionItem.create("a1b2c3d4-e5f6-7890-abcd-ef1234567890", 86400)
    >>> item.connectionId
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """

    connectionId: str
    timestamp: int
    ttl: int

    @classmethod
    def create(cls, connection_id: str, ttl_seconds: int) -> "ConnectionItem":
        """Create a new connection item with TTL.

        Parameters
        ----------
        connection_id : str
            WebSocket connection ID from API Gateway
        ttl_seconds : int
            Time-to-live in seconds from current time

        Returns
        -------
        ConnectionItem
            New connection item with calculated TTL timestamp
        """
        current_time = int(time.time())
        return cls(connectionId=connection_id, timestamp=current_time, ttl=current_time + ttl_seconds)


class ExecutionItem(BaseModel):
    """HITL workflow execution item for DynamoDB storage.

    Flat structure for efficient querying and GSI creation. Supports both
    UITakeover and Approval workflow types with type-specific optional fields.

    Attributes
    ----------
    eventId : str
        Event identifier (primary key)
    connectionId : str
        WebSocket connection identifier
    executionArn : str
        Step Function execution ARN
    workflowRunId : str
        Workflow run identifier
    sessionId : str
        Session identifier
    actId : str
        Act identifier
    interventionType : UseCase
        Type of intervention (UITakeover or Approval)
    timeout : int
        Timeout in seconds
    notificationRecipients : List[GenericDict]
        List of notification recipients (serialized NotificationRecipient objects)
    executionStatus : ExecutionStatus
        Current execution status
    createdAt : int
        Unix timestamp when execution was created
    updatedAt : int
        Unix timestamp when item was last updated
    ttl : int
        Unix timestamp when item should expire (for DynamoDB TTL)
    executionEndpoint : str
        Endpoint to the execution stack (e.g. WebSocket, REST API)
    message : str, optional
        UITakeover workflow: Message to display to the human
    remoteBrowserSessionId : str, optional
        UITakeover workflow: Remote browser session ID for browser control
    query : str, optional
        Approval workflow: Question to present for approval
    options : List[GenericDict], optional
        Approval workflow: List of approval options with label and action
    mostRecentScreenshot : str, optional
        Approval workflow: Base64-encoded screenshot for context
    approvalAction : str, optional
        Approval workflow: Normalized approval action (APPROVE or DENY)
    """

    eventId: str
    connectionId: str
    executionArn: str
    workflowRunId: str
    sessionId: str
    actId: str
    interventionType: UseCase
    timeout: int
    notificationRecipients: List[GenericDict]
    executionStatus: ExecutionStatus
    createdAt: int
    updatedAt: int
    ttl: int
    executionEndpoint: str

    # UITakeover specific fields
    message: str | None = None
    remoteBrowserSessionId: str | None = None

    # Approval specific fields
    query: str | None = None
    options: List[GenericDict] | None = None  # Serialized ApprovalOption objects
    mostRecentScreenshot: str | None = None
    approvalAction: str | None = None

    # Slack threading support - stores the thread timestamp for threaded notifications
    slackThreadTs: str | None = None

    # Error information for FAILED status
    errorDetails: GenericDict | None = None  # Serialized ErrorDetails object

    @classmethod
    def from_step_function_input(
        cls,
        event_id: str,
        connection_id: str,
        execution_arn: str,
        step_function_input: InterventionRequest,
        ttl_seconds: int,
        execution_endpoint: str,
        execution_status: ExecutionStatus = ExecutionStatus.IN_PROGRESS,
    ) -> "ExecutionItem":
        """Create a new execution item from Step Function input with calculated TTL and timestamps.

        Parameters
        ----------
        event_id : str
            Event identifier for this execution
        connection_id : str
            WebSocket connection ID from API Gateway
        execution_arn : str
            Step Function execution ARN
        step_function_input : InterventionRequest
            Step Function input data (UITakeoverStepFunctionInput or ApprovalStepFunctionInput)
        ttl_seconds : int
            Time-to-live in seconds from current time
        execution_endpoint : str
            Endpoint to the execution stack (e.g., WebSocket URL)
        execution_status : ExecutionStatus, default=ExecutionStatus.IN_PROGRESS
            Initial execution status

        Returns
        -------
        ExecutionItem
            New execution item with calculated TTL and workflow-specific fields

        Raises
        ------
        ValueError
            If step_function_input type is not supported (not UITakeover or Approval)

        Examples
        --------
        UITakeover workflow execution item::

            {
                "eventId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "connectionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "executionArn": "arn:aws:states:us-east-1:123456789012:execution:MyStateMachine:execution-name",
                "workflowRunId": "12345678-1234-1234-1234-123456789012",
                "sessionId": "87654321-4321-4321-4321-210987654321",
                "actId": "abcdef12-3456-7890-abcd-ef1234567890",
                "interventionType": "UITakeover",
                "timeout": 86400,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "user@example.com"}}],
                "message": "Please complete the form submission",
                "remoteBrowserSessionId": "01K7QQZ3BDK9HBE6KT05MSQHK6",
                "executionStatus": "IN_PROGRESS",
                "createdAt": 1703097600,
                "updatedAt": 1703097600,
                "ttl": 1703184000,
                "executionEndpoint": "wss://api.example.com/ws"
            }

        Approval workflow execution item::

            {
                "eventId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "connectionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "executionArn": "arn:aws:states:us-east-1:123456789012:execution:MyStateMachine:execution-name",
                "workflowRunId": "12345678-1234-1234-1234-123456789012",
                "sessionId": "87654321-4321-4321-4321-210987654321",
                "actId": "abcdef12-3456-7890-abcd-ef1234567890",
                "interventionType": "Approval",
                "timeout": 86400,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "user@example.com"}}],
                "query": "Do you approve this purchase order for $1,500?",
                "options": [{"label": "Approve", "action": "APPROVE"}, {"label": "Cancel", "action": "DENY"}],
                "mostRecentScreenshot": "data:image/png;base64,iVBRU5ErkJggg==",
                "approvalAction": "APPROVE",
                "executionStatus": "COMPLETED",
                "createdAt": 1703097600,
                "updatedAt": 1703097650,
                "ttl": 1703184000,
                "executionEndpoint": "wss://api.example.com/ws"
            }
        """
        current_time = int(time.time())
        notification_recipients = [r.model_dump() for r in step_function_input.notification_recipients]

        # Common fields for all intervention types
        common_fields: GenericDict = {
            "eventId": event_id,
            "connectionId": connection_id,
            "executionArn": execution_arn,
            "workflowRunId": step_function_input.workflow_run_id,
            "sessionId": step_function_input.session_id,
            "actId": step_function_input.act_id,
            "interventionType": step_function_input.type,
            "timeout": step_function_input.timeout,
            "notificationRecipients": notification_recipients,
            "executionStatus": execution_status,
            "createdAt": current_time,
            "updatedAt": current_time,
            "ttl": current_time + ttl_seconds,
            "executionEndpoint": execution_endpoint,
        }

        if isinstance(step_function_input, UITakeoverStepFunctionInput):
            return cls(
                **common_fields,
                message=step_function_input.message,
                remoteBrowserSessionId=step_function_input.remote_browser.session_id,
            )
        elif isinstance(step_function_input, ApprovalStepFunctionInput):
            # Serialize ApprovalOption objects to dictionaries for DynamoDB storage
            options = [opt.model_dump() for opt in step_function_input.options]
            return cls(
                **common_fields,
                query=step_function_input.query,
                options=options,
                mostRecentScreenshot=step_function_input.most_recent_screenshot,
            )
        raise ValueError(f"Unsupported intervention type: {step_function_input.type}")

    def get_notification_recipients(self) -> List[NotificationRecipient]:
        """Convert notification recipients to objects.

        Returns
        -------
        List[NotificationRecipient]
            List of deserialized NotificationRecipient objects
        """
        return [NotificationRecipient(**r) for r in self.notificationRecipients]

    def get_approval_options(self) -> List[ApprovalOption] | None:
        """Convert approval options to ApprovalOption objects.

        Returns
        -------
        List[ApprovalOption] or None
            List of deserialized ApprovalOption objects, or None if options not set
        """
        if self.options is None:
            return None
        return [ApprovalOption(**opt) for opt in self.options]

    def get_error_details(self) -> ErrorDetails | None:
        """Convert error details to ErrorDetails object.

        Returns
        -------
        ErrorDetails or None
            Deserialized ErrorDetails object, or None if errorDetails not set
        """
        if self.errorDetails is None:
            return None
        return ErrorDetails(**self.errorDetails)
