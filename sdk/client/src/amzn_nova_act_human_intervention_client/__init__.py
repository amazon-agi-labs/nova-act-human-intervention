"""Amazon Nova Act Human Intervention Client.

This package provides a client library for implementing human-in-the-loop (HITL)
interventions in automated workflows. It supports two types of interventions:

1. **Approval**: Request human approval or decision-making with optional screenshots
2. **UI Takeover**: Allow humans to take control of browser sessions for complex tasks

Key Features
------------
- WebSocket-based real-time communication
- Automatic credential management and refresh
- Long-running workflow support (up to 24 hours)
- Connection keep-alive and auto-reconnection
- S3 integration for screenshot storage (Approval workflows)
- Email notifications to intervention recipients

Quick Start
-----------
Basic approval workflow:

>>> from amzn_nova_act_human_intervention_client import (
...     ApprovalInterventionExecutor,
...     AssumedRoleCredentialsProvider
... )
>>> from amzn_nova_act_human_intervention_common import (
...     ApprovalRequest,
...     InterventionContext,
...     EmailContactInfo
... )
>>>
>>> # Set up credentials
>>> credentials = AssumedRoleCredentialsProvider(
...     role_arn="arn:aws:iam::123456789012:role/MyRole",
...     duration_seconds=3600
... )
>>>
>>> # Create intervention context
>>> context = InterventionContext(
...     workflow_run_id="run-123",
...     act_session_id="session-456",
...     act_id="act-789"
... )
>>>
>>> # Create and run approval executor
>>> executor = ApprovalInterventionExecutor(
...     endpoint="wss://myapi.execute-api.us-west-2.amazonaws.com/prod",
...     intervention_context=context,
...     screenshot_s3_bucket="my-screenshots-bucket",
...     credentials_provider=credentials
... )
>>>
>>> approval = ApprovalRequest(
...     question="Should we proceed?",
...     most_recent_screenshot="data:image/png;base64,...",
...     notification_recipients=[EmailContactInfo(email="user@example.com")]
... )
>>>
>>> executor.run(approval)
>>> print(executor.completion_response["approvalAction"])

Modules
-------
credentials
    AWS credential providers for authentication
executors
    Intervention executor implementations (Approval, UI Takeover)
exceptions
    Custom exceptions for workflow errors
utils
    Configuration constants and utilities

See Also
--------
ApprovalInterventionExecutor : Execute approval workflows
UITakeoverInterventionExecutor : Execute UI takeover workflows
AssumedRoleCredentialsProvider : AWS STS-based credential provider
WorkflowExecutionError : Exception for workflow termination
"""

from amzn_nova_act_human_intervention_common import (
    ApprovalRequest,
    ApprovalStepFunctionInput,
    BrowserSessionContext,
    ExecutorRequest,
    InterventionContext,
    LoggingConfig,
    StepFunctionInput,
    UITakeoverRequest,
    UITakeoverStepFunctionInput,
    UseCase,
)

from amzn_nova_act_human_intervention_client.credentials import (
    AssumedRoleCredentialsProvider,
    CredentialsProvider,
)
from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors import (
    ApprovalInterventionExecutor,
    BaseInterventionExecutor,
    ExecutorType,
    UITakeoverInterventionExecutor,
    WebsocketBasedInterventionExecutor,
)
from amzn_nova_act_human_intervention_client.utils import constants

__all__ = [
    "BaseInterventionExecutor",
    "WebsocketBasedInterventionExecutor",
    "ExecutorType",
    "UITakeoverInterventionExecutor",
    "ApprovalInterventionExecutor",
    # Credentials
    "CredentialsProvider",
    "AssumedRoleCredentialsProvider",
    # Exceptions
    "WorkflowExecutionError",
    # Models
    "UseCase",
    "UITakeoverRequest",
    "ApprovalRequest",
    "InterventionContext",
    "BrowserSessionContext",
    "StepFunctionInput",
    "UITakeoverStepFunctionInput",
    "ApprovalStepFunctionInput",
    "ExecutorRequest",
    # Logging
    "LoggingConfig",
    # Constants
    "constants",
]

__version__ = "1.0.0"
