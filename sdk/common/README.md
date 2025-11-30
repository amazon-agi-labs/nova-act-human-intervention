# Amazon Nova Act Human Intervention Common

Shared models, types, and utilities for the Nova Act Human Intervention service. This package provides the common data structures and type definitions used by both the backend service (`amzn_nova_act_human_intervention`) and client library (`amzn_nova_act_human_intervention_client`).

## Purpose

This package serves as the contract layer between the client and backend, ensuring type safety and consistency across the entire Human-in-the-Loop (HITL) system. By centralizing models in a shared package, we ensure that:

- **Type Safety**: Both client and backend use identical data structures
- **API Contract**: Changes to models are reflected across the entire system
- **No Duplication**: Models are defined once and imported where needed
- **Version Compatibility**: Client and backend can verify compatibility through shared types

## Package Structure

```
src/amzn_nova_act_human_intervention_common/
├── models/
│   ├── common_models.py           # UseCase, NotificationChannel, NotificationRecipient
│   ├── request_models.py          # HITLRequest, ApprovalRequest, UITakeoverRequest
│   ├── step_function_models.py    # Step Functions input models
│   ├── intervention_models.py     # InterventionContext, BrowserSessionContext
│   ├── dynamodb_models.py         # ExecutionItem, ConnectionItem, ExecutionStatus
│   ├── executor_models.py         # ExecutorRequest
│   └── type_definitions.py        # JSONType, GenericDict, InterventionRequest
├── config/
│   └── logging_config.py          # LoggingConfig for consistent logging
└── utils/
    ├── aws_sigv4_signer.py        # AWSSigV4Signer for WebSocket authentication
    └── utils.py                   # General utilities (JSON validation, etc.)
```

## Core Models

### Request Models

Models used by clients to initiate interventions:

```python
from amzn_nova_act_human_intervention_common import (
    ApprovalRequest,
    UITakeoverRequest,
    NotificationRecipient,
    EmailContactInfo,
    SlackContactInfo,
    ApprovalOption,
    ApprovalAction,
)

# Approval pattern request
approval_request = ApprovalRequest(
    question="Do you approve this purchase?",
    options=[
        ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
        ApprovalOption(label="Deny", action=ApprovalAction.DENY),
    ],
    notification_recipients=[
        NotificationRecipient(
            contact_info=EmailContactInfo(email_address="user@example.com")
        )
    ],
    most_recent_screenshot="data:image/png;base64,...",
    timeout=7200
)
```

### Intervention Context

Identifies the Nova Act workflow run and integrates with Nova Act:

```python
from amzn_nova_act_human_intervention_common import InterventionContext

context = InterventionContext(
    workflow_run_id="550e8400-e29b-41d4-a716-446655440000",  # Unique Nova Act workflow ID
    act_session_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",  # Nova Act session
    act_id="6ba7b811-9dad-11d1-80b4-00c04fd430c8"           # Nova Act instance
)
```

### DynamoDB Models

Backend storage models for execution tracking:

```python
from amzn_nova_act_human_intervention_common import (
    ExecutionItem,
    ExecutionStatus,
    ConnectionItem
)

# Create execution record
execution = ExecutionItem.create(
    event_id="unique-event-id",
    connection_id="websocket-connection-id",
    execution_arn="arn:aws:states:...",
    step_function_input=step_function_input,
    ttl_seconds=86400,
    execution_endpoint="wss://...",
    execution_status=ExecutionStatus.IN_PROGRESS
)

# Check status
if execution.executionStatus == ExecutionStatus.COMPLETED:
    print("Intervention completed")
```

### Step Function Models

Models for Step Functions pattern inputs:

```python
from amzn_nova_act_human_intervention_common import (
    ApprovalStepFunctionInput,
    UITakeoverStepFunctionInput,
    UseCase
)

# Automatically deserialize from payload
step_input = StepFunctionInput.from_payload(payload)

if isinstance(step_input, ApprovalStepFunctionInput):
    print(f"Approval query: {step_input.query}")
    print(f"Options: {step_input.options}")
elif isinstance(step_input, UITakeoverStepFunctionInput):
    print(f"Message: {step_input.message}")
    print(f"Browser session: {step_input.remote_browser.session_id}")
```

## Usage Across Packages

### In amzn_nova_act_human_intervention_client (Client Library)

The client uses common models to construct requests and parse responses:

```python
from amzn_nova_act_human_intervention_client import ApprovalInterventionExecutor
from amzn_nova_act_human_intervention_common import (
    InterventionContext,
    ApprovalRequest,
    ApprovalOption,
    ApprovalAction,
    NotificationRecipient,
    EmailContactInfo,
    SlackContactInfo,
)

# Client constructs request using common models
request = ApprovalRequest(
    question="Approve purchase?",
    options=[
        ApprovalOption(label="Yes", action=ApprovalAction.APPROVE),
        ApprovalOption(label="No", action=ApprovalAction.DENY),
    ],
    notification_recipients=[
        NotificationRecipient(contact_info=EmailContactInfo(email_address="user@example.com"))
    ],
    most_recent_screenshot=screenshot_data_url,
)

# Send to backend
executor.run(request)
```

### In amzn_nova_act_human_intervention (Backend Service)

The backend uses common models to process requests and manage execution state:

```python
from amzn_nova_act_human_intervention_common import (
    StepFunctionInput,
    ExecutionItem,
    ExecutionStatus,
    ApprovalStepFunctionInput,
)

# Backend receives and deserializes
step_input = StepFunctionInput.from_payload(event["input"])

# Create execution record
execution_item = ExecutionItem.create(
    event_id=event_id,
    connection_id=connection_id,
    execution_arn=execution_arn,
    step_function_input=step_input,
    ttl_seconds=86400,
    execution_endpoint=websocket_endpoint,
)

# Store in DynamoDB
executions_table.put_item(Item=execution_item.model_dump())

# Generate SPA based on type
if isinstance(step_input, ApprovalStepFunctionInput):
    spa_html = generate_approval_spa(
        question=step_input.query,
        options=step_input.get_approval_options(),
        screenshot=step_input.most_recent_screenshot,
    )
```

## Key Features

### Type Definitions

Provides common type aliases for consistent typing:

```python
from amzn_nova_act_human_intervention_common import (
    JSONType,          # Union of JSON-serializable types
    GenericDict,       # Dict[str, Any]
    InterventionRequest # Union of ApprovalStepFunctionInput | UITakeoverStepFunctionInput
)
```

### Enumerations

Type-safe enumerations for execution states and options:

```python
# Use cases
UseCase.APPROVAL           # "Approval"
UseCase.UI_TAKEOVER        # "UITakeover"

# Notification channels
NotificationChannel.EMAIL  # "Email"
NotificationChannel.SLACK  # "Slack"

# Approval actions
ApprovalAction.APPROVE     # "APPROVE"
ApprovalAction.DENY        # "DENY"

# Execution statuses
ExecutionStatus.IN_PROGRESS         # "IN_PROGRESS"
ExecutionStatus.PENDING_HUMAN_INPUT # "PENDING_HUMAN_INPUT"
ExecutionStatus.COMPLETED           # "COMPLETED"
ExecutionStatus.FAILED              # "FAILED"
ExecutionStatus.TERMINATED          # "TERMINATED"
```

### Utilities

#### AWS SigV4 Signer

Sign WebSocket URLs for secure connections:

```python
from amzn_nova_act_human_intervention_common import AWSSigV4Signer
from botocore.credentials import Credentials

signer = AWSSigV4Signer(region="us-west-2", service="execute-api")
signed_url = signer.sign_websocket_url(
    websocket_url="wss://api-id.execute-api.us-west-2.amazonaws.com/alpha",
    credentials=credentials,
    expires_in=3600
)
```

#### Logging Configuration

Consistent logging across Lambda and local environments:

```python
from amzn_nova_act_human_intervention_common import LoggingConfig

logger = LoggingConfig.get_logger(__name__)
logger.info("Processing intervention request")
```

## Documentation Style

All models and utilities follow NumPy/SciPy docstring conventions for consistency:

```python
def method_name(param: str, optional_param: int = 10) -> bool:
    """Brief description.

    Parameters
    ----------
    param : str
        Description of param
    optional_param : int, default=10
        Description of optional param

    Returns
    -------
    bool
        Description of return value

    Examples
    --------
    >>> method_name("test")
    True
    """
```

## Development

### Testing

Run unit tests:
```bash
hatch test
```

### Type Checking

Run mypy:
```bash
hatch run typing
```

## Versioning

This package version should be kept in sync with both `amzn_nova_act_human_intervention` and `amzn_nova_act_human_intervention_client` to ensure compatibility. Breaking changes to models require coordinated updates across all three packages.

## Installation

For use in other packages:

```bash
# For local development
pip install -e /path/to/amzn_nova_act_human_intervention_common
```

## License

See LICENSE file for details.
