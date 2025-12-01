# Amazon Nova Act Human Intervention Service Client SDK

Python client library for integrating Human-in-the-Loop (HITL) interventions into Nova Act workflows. Provides executors for Approval and UI Takeover patterns that connect to the backend service via WebSocket.

## Overview

This client library enables automated agents (like Nova Act) to request human intervention when needed:

- **Approval Pattern**: Request human approval for decisions (e.g., "Should I purchase this item for $1,500?")
- **UI Takeover Pattern**: Request human assistance with complex UI interactions (e.g., CAPTCHAs, form filling)

## Installation

### Basic Installation

For standalone usage (Approval and UI Takeover patterns without Nova Act):

```bash
# Install both client and common packages
pip install amzn-nova-act-human-intervention-client amzn-nova-act-human-intervention-common
```

### Full Installation with Nova Act Integration

For complete integration with Nova Act and Bedrock Agent (required for usage examples):

```bash
# Install HITL packages
pip install amzn-nova-act-human-intervention-client amzn-nova-act-human-intervention-common

# Install Nova Act (see https://nova.amazon.com/act for setup instructions)
pip install nova-act

# Install Bedrock Agent Core (for browser session support)
pip install bedrock-agentcore
```

**Note**: Nova Act installation requires additional setup and credentials. Refer to the [Nova Act documentation](https://nova.amazon.com/act) for detailed installation and configuration instructions.

## Complete Usage Examples

For complete, ready-to-run examples with full Nova Act integration, see the **[../../samples/](../../samples/)** folder:
- **[standalone-hitl-run.py](../../samples/standalone-hitl-run.py)** - Standalone examples demonstrating Approval and UI Takeover patterns
- **[nova-act-integration.py](../../samples/nova-act-integration.py)** - Full Nova Act integration with HumanInputCallbacks implementation
- **[samples/README.md](../../samples/README.md)** - Comprehensive documentation with setup, configuration, and troubleshooting

These examples show real-world usage patterns with proper error handling, credential management, and notification setup.

## Key Features

- **WebSocket-based Communication**: Real-time bidirectional communication with backend
- **SigV4 Authentication**: Secure AWS credential-based authentication
- **Long-Running Support**: Up to 24 hours execution with automatic URL refresh and reconnection
- **Automatic Credential Refresh**: Handles credential rotation before expiration
- **Resilient Connection**: Exponential backoff retry for transient network failures
- **Screenshot Support**: Upload and embed screenshots for approval context (Approval pattern only)
- **S3 Integration**: Automatic S3 upload for screenshots
- **Blocking Execution**: Waits for human response before continuing
- **Multi-Channel Notifications**: Email and Slack notification support

## Quick Start

### Approval Pattern Example

Request human approval with a screenshot for context:

```python
import boto3
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    AssumedRoleCredentialsProvider,
)
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    ApprovalRequest,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
)

# Create intervention context with workflow identifiers
context = InterventionContext(
    workflow_run_id="<UUID4>",
    act_session_id="<UUID4>",
    act_id="<UUID4>",
)

# Create boto3 session (uses default credentials or AWS_PROFILE)
boto_session = boto3.Session(region_name="<region you have deployed the service to>")

# Create credentials provider for IAM role assumption
credentials_provider = AssumedRoleCredentialsProvider(
    role_arn="arn:aws:iam::ACCOUNT_ID:role/NovaAct-HITL-ExecutionRole",
    duration_seconds=7200,  # 2 hours
    session=boto_session
)

# Initialize the Approval executor
executor = ApprovalInterventionExecutor(
    endpoint="wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/alpha",
    intervention_context=context,
    screenshot_s3_bucket="your-screenshot-bucket",
    credentials_provider=credentials_provider,
    region="<region you have deployed the service to>",
    execution_timeout=7200
)

# Load screenshot as Base64 data URL
screenshot_data_url = load_screenshot_as_data_url("screenshot.png")

# Execute the approval pattern (blocks until user responds)
executor.run(
    ApprovalRequest(
        question="Do you approve this purchase order for $1,500?",
        options=[
            ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
            ApprovalOption(label="Deny", action=ApprovalAction.DENY),
        ],
        notification_recipients=[
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user@example.com",
                    from_email_address="noreply@example.com"
                )
            )
        ],
        most_recent_screenshot=screenshot_data_url,
    )
)

# Check the result
if executor.completion_response["approvalAction"] == "APPROVE":
    print("User approved the action")
else:
    print("User denied the action")
```

### UI Takeover Pattern Example

Request human interaction with a browser session:

```python
import boto3
from amzn_nova_act_human_intervention_client import (
    AssumedRoleCredentialsProvider,
    UITakeoverInterventionExecutor,
)
from amzn_nova_act_human_intervention_common import (
    BrowserSessionContext,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
    UITakeoverRequest,
)

# Create intervention context
context = InterventionContext(
    workflow_run_id="<UUID4>",
    act_session_id="<UUID4>",
    act_id="<UUID4>",
)

# Create boto3 session (uses default credentials or AWS_PROFILE)
boto_session = boto3.Session(region_name="<region you have deployed the service to>")

# Create credentials provider
credentials_provider = AssumedRoleCredentialsProvider(
    role_arn="arn:aws:iam::ACCOUNT_ID:role/NovaAct-HITL-ExecutionRole",
    duration_seconds=7200,
    session=boto_session
)

# Initialize the UI Takeover executor
executor = UITakeoverInterventionExecutor(
    endpoint="wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/alpha",
    intervention_context=context,
    credentials_provider=credentials_provider,
    region="<region you have deployed the service to>",
    execution_timeout=7200
)

# Execute the UI takeover pattern (blocks until user completes)
executor.run(
    UITakeoverRequest(
        message="Please complete the CAPTCHA verification",
        browser_session=BrowserSessionContext(session_id="<browser-session-id>"),
        notification_recipients=[
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user@example.com",
                    from_email_address="noreply@example.com"
                )
            )
        ],
    )
)

print("User completed the UI takeover task")
```

### Using Slack Notifications

Both Approval and UI Takeover patterns support Slack notifications in addition to email:

```python
from amzn_nova_act_human_intervention_common import (
    NotificationRecipient,
    SlackContactInfo,
    SlackTargetType,
)

# Notify a specific Slack user
notification_recipients=[
    NotificationRecipient(
        contact_info=SlackContactInfo(
            channel="#general",
            target="@username",  # or user ID like "U12345"
            target_type=SlackTargetType.USER
        )
    )
]

# Notify a Slack user group
notification_recipients=[
    NotificationRecipient(
        contact_info=SlackContactInfo(
            channel="#incident-response",
            target="S12345",  # User group ID
            target_type=SlackTargetType.USERGROUP
        )
    )
]

# Notify multiple recipients (email and Slack)
notification_recipients=[
    NotificationRecipient(
        contact_info=EmailContactInfo(
            to_email_address="user@example.com",
            from_email_address="noreply@example.com"
        )
    ),
    NotificationRecipient(
        contact_info=SlackContactInfo(
            channel="#alerts",
            target="@oncall",
            target_type=SlackTargetType.USER
        )
    )
]
```

## Integration with Nova Act

### Amazon Bedrock AgentCore Browser Sessions

When integrating with Nova Act, you'll use [Amazon Bedrock AgentCore Browser](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool.html) to provide a secure, cloud-based browser environment for your agent workflows. The AgentCore Browser is a fully managed service that enables AI agents to interact with websites, fill forms, navigate web applications, and extract information.

The `browser_session` context manager from `bedrock_agentcore.tools.browser_client` provides:

- **Managed Browser Sessions**: Automatically creates and tears down cloud-based browser instances
- **WebSocket Connectivity**: Generates WebSocket URLs and headers for Chrome DevTools Protocol (CDP) connections
- **Session Management**: Handles browser session lifecycle, including timeout configuration and cleanup
- **DCV Streaming**: Enables live browser streaming for UI Takeover patterns via Amazon DCV protocol

**Basic Usage:**

```python
from bedrock_agentcore.tools.browser_client import browser_session

with browser_session(aws_region) as agent_core_browser:
    # Get WebSocket URL and headers for CDP connection
    ws_url, headers = agent_core_browser.generate_ws_headers()

    # Get the browser session ID (used for UI Takeover patterns)
    session_id = agent_core_browser.session_id

    # Use with Nova Act or other browser automation tools
    # The browser session remains active within this context
```

**Key Properties:**
- `session_id`: Unique identifier for the browser session (required for UI Takeover patterns)
- `generate_ws_headers()`: Returns WebSocket URL and authentication headers for CDP connections
- Automatically starts the browser session on context entry and stops it on exit

For more details, see:
- [Starting a browser session](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-start-session.html)
- [Get Browser session](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-session-get.html)
- [Using AgentCore Browser with other tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-building-agents.html)

### Nova Act Callbacks Implementation

The client library can be integrated with Nova Act through callbacks:

```python
import boto3
from nova_act.nova_act import HumanInputCallbacksBase, NovaAct
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    AssumedRoleCredentialsProvider,
    UITakeoverInterventionExecutor,
)

class NovaActHumanInputCallbacks(HumanInputCallbacksBase):
    """Implementation of HumanInputCallbacksBase for Nova Act integration."""

    def __init__(self, browser_session_id: str = None, region: str = "<region you have deployed the service to>"):
        super().__init__()
        self._browser_session_id = browser_session_id
        self._region = region
        # Create boto3 session for credentials
        self._boto_session = boto3.Session(region_name=region)
        self._credentials_provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::ACCOUNT_ID:role/NovaAct-HITL-ExecutionRole",
            duration_seconds=7200,
            session=self._boto_session
        )

    def approve(self, message: str) -> bool:
        """Request human approval."""
        context = InterventionContext(
            workflow_run_id=str(uuid.uuid4()),
            act_session_id=self.act_session_id,
            act_id=self.current_act_id,
        )

        executor = ApprovalInterventionExecutor(
            endpoint="wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/alpha",
            intervention_context=context,
            screenshot_s3_bucket="your-screenshot-bucket",
            credentials_provider=self._credentials_provider,
            region=self._region,
            execution_timeout=7200,
        )

        executor.run(
            ApprovalRequest(
                question=message,
                options=[
                    ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
                    ApprovalOption(label="Deny", action=ApprovalAction.DENY),
                ],
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="user@example.com",
                            from_email_address="noreply@example.com"
                        )
                    )
                ],
                most_recent_screenshot=self.most_recent_screenshot,
            )
        )

        return executor.completion_response["approvalAction"] == "APPROVE"

    def ui_takeover(self, message: str) -> None:
        """Request human UI interaction."""
        context = InterventionContext(
            workflow_run_id=str(uuid.uuid4()),
            act_session_id=self.act_session_id,
            act_id=self.current_act_id,
        )

        executor = UITakeoverInterventionExecutor(
            endpoint="wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/alpha",
            intervention_context=context,
            credentials_provider=self._credentials_provider,
            region=self._region,
            execution_timeout=7200,
        )

        executor.run(
            UITakeoverRequest(
                message=message,
                browser_session=BrowserSessionContext(session_id=self._browser_session_id),
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="user@example.com",
                            from_email_address="noreply@example.com"
                        )
                    )
                ],
            )
        )

# Use with Nova Act
from bedrock_agentcore.tools.browser_client import browser_session
from nova_act.nova_act import Workflow

aws_region = "<region you have deployed the service to>"
workflow_boto_session_args = {"region_name": aws_region}

with browser_session(aws_region) as agent_core_browser:
    ws_url, headers = agent_core_browser.generate_ws_headers()
    with Workflow(
        boto_session_kwargs=workflow_boto_session_args,
        model_id="nova-act-latest",
        workflow_definition_name="nova-act-hitl-example",
    ) as workflow:
        callbacks = NovaActHumanInputCallbacks(
            workflow_run_id=workflow.workflow_run_id,
            aws_region=aws_region,
            executor_endpoint="wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/prod",
            execution_timeout=7200,
            executor_iam_role_arn="arn:aws:iam::<account-id>:role/<your-role-name>",
            screenshot_s3_bucket="<your-screenshot-bucket>",
            browser_session_id=agent_core_browser.session_id,
            boto_session=boto3.Session(**workflow_boto_session_args),
        )

        with NovaAct(
            cdp_endpoint_url=ws_url,
            cdp_headers=headers,
            starting_page="https://www.example.com",
            tty=False,
            human_input_callbacks=callbacks,
            workflow=workflow,
        ) as nova:
            result = nova.act_get("Complete the purchase, but ask for approval before confirming")
            print(f"Task completed: {result}")
```

## How It Works

### Approval Pattern

1. **Client uploads screenshot**: Screenshot data URL is uploaded to S3 as text file
2. **WebSocket connection**: Client connects to WebSocket API using SigV4 signed URL
3. **Send request**: Client sends ApprovalRequest with question, options, and S3 presigned URL for screenshot
4. **Backend generates SPA**: Backend downloads screenshot, generates HTML SPA, uploads to CloudFront
5. **User notification**: User receives email/Slack notification with SPA URL
6. **User responds**: User opens SPA, views screenshot + question, clicks Approve/Deny
7. **Response via WebSocket**: Backend sends completion message to client
8. **Client returns**: `executor.run()` returns, caller checks `completion_response["approvalAction"]`

### UI Takeover Pattern

1. **WebSocket connection**: Client connects to WebSocket API using SigV4 signed URL
2. **Send request**: Client sends UITakeoverRequest with message and browser session ID
3. **Backend generates SPA**: Backend generates HTML SPA with embedded browser interface
4. **User notification**: User receives email/Slack notification with SPA URL
5. **User interacts**: User opens SPA, controls browser, completes task, clicks Submit
6. **Response via WebSocket**: Backend sends completion message to client
7. **Client returns**: `executor.run()` returns, caller continues execution

## Credentials Management

The library uses `AssumedRoleCredentialsProvider` to manage AWS credentials:

```python
import boto3

# Create boto3 session (required parameter)
boto_session = boto3.Session(profile_name="your-profile", region_name="<region you have deployed the service to>")

credentials_provider = AssumedRoleCredentialsProvider(
    role_arn="arn:aws:iam::ACCOUNT_ID:role/NovaAct-HITL-ExecutionRole",
    duration_seconds=7200,  # Credentials expire after 2 hours
    session=boto_session  # Required: boto3 Session instance
)
```

The provider:
- Automatically assumes the specified IAM role via STS
- Refreshes credentials before expiration (with configurable buffer)
- Provides credentials for both WebSocket SigV4 signing and S3 operations
- **Environment-aware**: On AWS (ECS/Lambda/EC2), uses IAM role credentials automatically. Locally, creates fresh sessions to pick up updated credentials from credential providers.

### Long-Running Patterns (Up to 24 Hours)

The executors support patterns running up to 24 hours with built-in resilience features:

- **Automatic URL Refresh**: WebSocket URLs expire after 1 hour due to IAM role-chaining limits. The executor automatically refreshes the URL and reconnects before expiration.
- **Automatic Reconnection**: If the connection drops unexpectedly, the executor retries with exponential backoff (1s, 2s, 4s, ..., up to 30s) until the pattern completes or timeout is reached.
- **Credential Refresh**: Credentials are automatically refreshed before expiration to prevent authentication failures during long-running patterns.

For patterns longer than 1 hour, you need credentials that automatically refresh. The **recommended approach** is using AWS `credential_process`:

#### Setup credential_process

1. **Create a script that fetches credentials** (e.g., `get-credentials.sh`):

```bash
#!/bin/bash
# Example: Fetch credentials from your internal system
# Must output JSON in this exact format:
{
  "Version": 1,
  "AccessKeyId": "ASIA...",
  "SecretAccessKey": "...",
  "SessionToken": "...",
  "Expiration": "2025-11-12T16:30:00Z"
}
```

2. **Configure your AWS profile** in `~/.aws/config`:

```ini
[profile nova-act-hitl]
credential_process = /path/to/get-credentials.sh
region = <region you have deployed the service to>
```

3. **Use the profile in your code**:

```python
# Create boto3 session with your credential_process profile
boto_session = boto3.Session(profile_name="nova-act-hitl", region_name="<region you have deployed the service to>")

# Pass to credentials provider
credentials_provider = AssumedRoleCredentialsProvider(
    role_arn="arn:aws:iam::ACCOUNT_ID:role/NovaAct-HITL-ExecutionRole",
    duration_seconds=7200,
    session=boto_session  # Will auto-refresh via credential_process!
)
```

**How it works:**
- boto3 calls your `credential_process` script automatically when credentials expire
- The library creates fresh boto3 sessions when refreshing, triggering your script
- Your pattern can run up to 24 hours without credential expiration errors
- The executor handles URL refresh and reconnection automatically
- No code changes needed - boto3 handles credential refresh automatically

**Alternative approaches:**
- **AWS SSO**: `aws configure sso` (boto3 can auto-refresh SSO tokens)
- **IAM User credentials**: Long-lived credentials (not recommended for production)

## Screenshot Handling (Approval Only)

### With Nova Act Integration (Recommended)

When using Nova Act's `HumanInputCallbacksBase`, screenshots are automatically provided by the framework:

```python
class NovaActHumanInputCallbacks(HumanInputCallbacksBase):
    def approve(self, message: str) -> bool:
        """Request human approval."""
        # Nova Act automatically provides most_recent_screenshot
        # No manual screenshot conversion needed!
        executor.run(
            ApprovalRequest(
                question=message,
                options=[...],
                notification_recipients=[...],
                most_recent_screenshot=self.most_recent_screenshot,  # Provided by Nova Act
            )
        )
```

The `most_recent_screenshot` field is automatically captured and formatted by Nova Act as a Base64-encoded data URL, ready to use directly in your approval requests.

### For Standalone Testing

When testing outside of Nova Act, you can manually convert images to data URLs:

```python
from PIL import Image
import base64
from io import BytesIO

def load_screenshot_as_data_url(image_path: str) -> str:
    """Load image and convert to Base64 data URL."""
    image = Image.open(image_path)

    format_to_mime = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    mime_type = format_to_mime.get(image.format, "image/jpeg")

    buffer = BytesIO()
    image.save(buffer, format=image.format or "JPEG")
    image_bytes = buffer.getvalue()

    base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{base64_encoded}"
```

### Screenshot Processing Flow

The client automatically:
1. Uploads the data URL to S3 as a text file
2. Provides presigned URL to backend
3. Backend downloads and embeds in SPA
4. Deletes screenshot from S3 after SPA generation

## Configuration

### Required IAM Permissions

The execution role needs:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "execute-api:ManageConnections",
                "execute-api:Invoke"
            ],
            "Resource": "arn:aws:execute-api:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::your-screenshot-bucket/*"
        }
    ]
}
```

### Cross-Account Access

When the client runs in a different AWS account than the backend service, you need to configure cross-account IAM role assumption.

**Backend Service Account (Account B - where HITL service is deployed):**

Update the execution role trust policy to allow assumption from a specific role in the client account:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::ACCOUNT_A_ID:role/NovaAct-Client-Role"
            },
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {
                    "sts:ExternalId": "optional-external-id-for-security"
                }
            }
        },
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

**Important**: Replace `NovaAct-Client-Role` with the actual IAM role name that your Nova Act client uses in Account A. This provides least-privilege access by only allowing a specific role to assume the backend service role.

**Client Account (Account A - where Nova Act runs):**

Create an IAM role/policy that allows assuming the backend service role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Resource": "arn:aws:iam::ACCOUNT_B_ID:role/NovaAct-HITL-ExecutionRole"
        }
    ]
}
```

**Client Code Configuration:**

```python
import boto3
from amzn_nova_act_human_intervention_client import AssumedRoleCredentialsProvider

# Create boto3 session
boto_session = boto3.Session(region_name="<region you have deployed the service to>")

# Assume role in the backend service account
credentials_provider = AssumedRoleCredentialsProvider(
    role_arn="arn:aws:iam::ACCOUNT_B_ID:role/NovaAgent-HITL-ExecutionRole",
    duration_seconds=7200,
    session=boto_session
    # Note: external_id parameter is not currently supported
)

# Use with executor as normal
executor = ApprovalInterventionExecutor(
    endpoint="wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/alpha",
    intervention_context=context,
    screenshot_s3_bucket="your-screenshot-bucket",
    credentials_provider=credentials_provider,
    region="<region you have deployed the service to>",
    execution_timeout=7200
)
```

**Key Points:**
- The client account needs a specific IAM role (e.g., `NovaAct-Client-Role`) with `sts:AssumeRole` permission for the backend service role
- The backend service role must trust the specific client role ARN (not `:root`) in its trust policy for least-privilege access
- The assumed role credentials are automatically used for all operations (WebSocket, S3)
- Credentials are refreshed automatically before expiration
- **Note**: External ID is shown in the trust policy example for reference but is not currently supported by the client library

### Environment Variables (Optional)

```bash
HITL_WEBSOCKET_ENDPOINT=wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/alpha
HITL_SCREENSHOT_S3_BUCKET=your-screenshot-bucket
HITL_IAM_ROLE_ARN=arn:aws:iam::ACCOUNT_ID:role/NovaAct-HITL-ExecutionRole
HITL_EXECUTION_TIMEOUT=7200
HITL_NOTIFICATION_EMAIL=user@example.com
AWS_REGION=<region you have deployed the service to>
```

## Complete Code Samples

**Note**: For fully working, runnable examples with command-line interfaces, see the **[../../samples/](../../samples/)** folder.

The examples below show the core usage patterns:

### Standalone Approval Pattern

Complete example showing approval pattern with screenshot upload:

```python
import base64
import uuid
from io import BytesIO
from pathlib import Path

import boto3
from PIL import Image
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    AssumedRoleCredentialsProvider,
)
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    ApprovalRequest,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
)


def load_screenshot_as_data_url(image_path: str) -> str:
    """Load image and convert to Base64 data URL."""
    image = Image.open(image_path)

    format_to_mime = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    mime_type = format_to_mime.get(image.format, "image/jpeg")

    buffer = BytesIO()
    image.save(buffer, format=image.format or "JPEG")
    image_bytes = buffer.getvalue()

    base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{base64_encoded}"


def main():
    # Configuration
    aws_region = "<region you have deployed the service to>"
    executor_endpoint = "wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/prod"
    executor_iam_role_arn = "arn:aws:iam::ACCOUNT_ID:role/NovaAgent-HITL-ExecutionRole"
    screenshot_s3_bucket = "your-screenshot-bucket"
    execution_timeout = 7200  # 2 hours

    # Create intervention context
    context = InterventionContext(
        workflow_run_id=str(uuid.uuid4()),
        act_session_id=str(uuid.uuid4()),
        act_id=str(uuid.uuid4()),
    )

    # Create boto3 session
    boto_session = boto3.Session(region_name=aws_region)

    # Create credentials provider
    credentials_provider = AssumedRoleCredentialsProvider(
        role_arn=executor_iam_role_arn,
        duration_seconds=execution_timeout,
        session=boto_session
    )

    # Initialize executor
    executor = ApprovalInterventionExecutor(
        endpoint=executor_endpoint,
        intervention_context=context,
        screenshot_s3_bucket=screenshot_s3_bucket,
        credentials_provider=credentials_provider,
        region=aws_region,
        execution_timeout=execution_timeout,
    )

    # Load screenshot
    screenshot_path = Path("screenshot.png")
    screenshot_data_url = load_screenshot_as_data_url(str(screenshot_path))

    # Execute approval pattern
    print("Starting Approval intervention pattern...")
    executor.run(
        ApprovalRequest(
            question="Do you approve this purchase order for $1,500?",
            options=[
                ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
                ApprovalOption(label="Deny", action=ApprovalAction.DENY),
            ],
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com",
                        from_email_address="noreply@example.com"
                    )
                )
            ],
            most_recent_screenshot=screenshot_data_url,
        )
    )

    # Check result
    print(f"Response: {executor.completion_response}")
    if executor.completion_response["approvalAction"] == "APPROVE":
        print("User approved the action")
    else:
        print("User denied the action")


if __name__ == "__main__":
    main()
```

### Standalone UI Takeover Pattern

Complete example showing UI takeover pattern with browser session:

```python
import uuid

import boto3
from bedrock_agentcore.tools.browser_client import browser_session
from amzn_nova_act_human_intervention_client import (
    AssumedRoleCredentialsProvider,
    UITakeoverInterventionExecutor,
)
from amzn_nova_act_human_intervention_common import (
    BrowserSessionContext,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
    UITakeoverRequest,
)


def main():
    # Configuration
    aws_region = "<region you have deployed the service to>"
    executor_endpoint = "wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/prod"
    executor_iam_role_arn = "arn:aws:iam::ACCOUNT_ID:role/NovaAgent-HITL-ExecutionRole"
    execution_timeout = 7200  # 2 hours

    # Create intervention context
    context = InterventionContext(
        workflow_run_id=str(uuid.uuid4()),
        act_session_id=str(uuid.uuid4()),
        act_id=str(uuid.uuid4()),
    )

    # Create boto3 session
    boto_session = boto3.Session(region_name=aws_region)

    # Create credentials provider
    credentials_provider = AssumedRoleCredentialsProvider(
        role_arn=executor_iam_role_arn,
        duration_seconds=execution_timeout,
        session=boto_session
    )

    # Initialize executor
    executor = UITakeoverInterventionExecutor(
        endpoint=executor_endpoint,
        intervention_context=context,
        credentials_provider=credentials_provider,
        region=aws_region,
        execution_timeout=execution_timeout,
    )

    # Execute UI takeover pattern with browser session
    print("Starting UI Takeover intervention pattern...")
    with browser_session(region=aws_region) as agent_browser:
        executor.run(
            UITakeoverRequest(
                message="Please complete the CAPTCHA verification",
                browser_session=BrowserSessionContext(session_id=agent_browser.session_id),
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="user@example.com",
                            from_email_address="noreply@example.com"
                        )
                    )
                ],
            )
        )

    print("User completed the UI takeover task")
    print(f"Response: {executor.completion_response}")


if __name__ == "__main__":
    main()
```

### Nova Act Integration Example

Complete example integrating with Nova Act callbacks:

```python
import uuid

import boto3
from nova_act.nova_act import HumanInputCallbacksBase, NovaAct
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    AssumedRoleCredentialsProvider,
    UITakeoverInterventionExecutor,
)
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    ApprovalRequest,
    BrowserSessionContext,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
    UITakeoverRequest,
)


class NovaActHumanInputCallbacks(HumanInputCallbacksBase):
    """Implementation of HumanInputCallbacksBase for Nova Act integration."""

    def __init__(
        self,
        executor_endpoint: str,
        executor_iam_role_arn: str,
        screenshot_s3_bucket: str,
        browser_session_id: str = None,
        region: str = "<region you have deployed the service to>",
        execution_timeout: int = 7200,
    ):
        super().__init__()
        self._executor_endpoint = executor_endpoint
        self._executor_iam_role_arn = executor_iam_role_arn
        self._screenshot_s3_bucket = screenshot_s3_bucket
        self._browser_session_id = browser_session_id
        self._region = region
        self._execution_timeout = execution_timeout

        # Create boto3 session and credentials provider
        self._boto_session = boto3.Session(region_name=region)
        self._credentials_provider = AssumedRoleCredentialsProvider(
            role_arn=executor_iam_role_arn,
            duration_seconds=execution_timeout,
            session=self._boto_session
        )

    def approve(self, message: str) -> bool:
        """Request human approval."""
        context = InterventionContext(
            workflow_run_id=str(uuid.uuid4()),
            act_session_id=self.act_session_id,
            act_id=self.current_act_id,
        )

        executor = ApprovalInterventionExecutor(
            endpoint=self._executor_endpoint,
            intervention_context=context,
            screenshot_s3_bucket=self._screenshot_s3_bucket,
            credentials_provider=self._credentials_provider,
            region=self._region,
            execution_timeout=self._execution_timeout,
        )

        executor.run(
            ApprovalRequest(
                question=message,
                options=[
                    ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
                    ApprovalOption(label="Deny", action=ApprovalAction.DENY),
                ],
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="user@example.com",
                            from_email_address="noreply@example.com"
                        )
                    )
                ],
                most_recent_screenshot=self.most_recent_screenshot,
            )
        )

        return executor.completion_response["approvalAction"] == "APPROVE"

    def ui_takeover(self, message: str) -> None:
        """Request human UI interaction."""
        context = InterventionContext(
            workflow_run_id=str(uuid.uuid4()),
            act_session_id=self.act_session_id,
            act_id=self.current_act_id,
        )

        executor = UITakeoverInterventionExecutor(
            endpoint=self._executor_endpoint,
            intervention_context=context,
            credentials_provider=self._credentials_provider,
            region=self._region,
            execution_timeout=self._execution_timeout,
        )

        executor.run(
            UITakeoverRequest(
                message=message,
                browser_session=BrowserSessionContext(session_id=self._browser_session_id),
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="user@example.com",
                            from_email_address="noreply@example.com"
                        )
                    )
                ],
            )
        )


def main():
    # Configuration
    aws_region = "<region you have deployed the service to>"
    executor_endpoint = "wss://YOUR_API_ID.execute-api.<region you have deployed the service to>.amazonaws.com/prod"
    executor_iam_role_arn = "arn:aws:iam::ACCOUNT_ID:role/NovaAgent-HITL-ExecutionRole"
    screenshot_s3_bucket = "your-screenshot-bucket"
    workflow_boto_session_args = {"region_name": aws_region}

    # Use with Nova Act
    with browser_session(aws_region) as agent_core_browser:
        ws_url, headers = agent_core_browser.generate_ws_headers()
        with Workflow(
            boto_session_kwargs=workflow_boto_session_args,
            model_id="nova-act-latest",
            workflow_definition_name="nova-act-hitl-example",
        ) as workflow:
            callbacks = NovaActHumanInputCallbacks(
                workflow_run_id=workflow.workflow_run_id,
                aws_region=aws_region,
                executor_endpoint=executor_endpoint,
                execution_timeout=7200,
                executor_iam_role_arn=executor_iam_role_arn,
                screenshot_s3_bucket=screenshot_s3_bucket,
                browser_session_id=agent_core_browser.session_id,
                boto_session=boto3.Session(**workflow_boto_session_args),
            )

            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                starting_page="https://www.example.com",
                tty=False,
                human_input_callbacks=callbacks,
                workflow=workflow,
            ) as nova:
                result = nova.act_get("Complete the purchase, but ask for approval before confirming")
                print(f"Task completed: {result}")


if __name__ == "__main__":
    main()
```

## Error Handling

The executors raise exceptions for different failure scenarios:

```python
from amzn_nova_act_human_intervention_client import WorkflowExecutionError

try:
    executor.run(request)
except TimeoutError:
    print("User did not respond within timeout period")
except ConnectionError:
    print("Failed to connect to WebSocket endpoint")
except WorkflowExecutionError as e:
    # User-initiated termination (TERMINATED status)
    # Handle gracefully - user explicitly cancelled the intervention
    print(f"Workflow terminated by user: {e}")
    print(f"  Status: {e.status}")
    print(f"  Workflow Type: {e.workflow_type}")
except RuntimeError as e:
    # Workflow execution failure (FAILED status, null status, or other errors)
    # These indicate system/workflow issues that need investigation
    print(f"Workflow execution failed: {e}")
```

**Exception Types:**
- `WorkflowExecutionError`: Raised only for TERMINATED status (user-initiated cancellation)
- `RuntimeError`: Raised for FAILED status, null status, or other workflow errors
- `TimeoutError`: User did not respond within the configured timeout
- `ConnectionError`: WebSocket connection issues

## Troubleshooting

### WebSocket Connection Fails

- Verify IAM role has `execute-api:ManageConnections` permission
- Check that endpoint URL is correct and accessible
- Ensure credentials are valid and not expired

### Screenshot Upload Fails

- Verify IAM role has `s3:PutObject` permission on screenshot bucket
- Check that bucket exists and is in the same region
- Ensure screenshot data URL is properly formatted

### Timeout Issues

- Increase `execution_timeout` parameter
- Check that notifications are being delivered to users
- Verify backend Step Functions workflow is running

## License

See LICENSE file for details.
