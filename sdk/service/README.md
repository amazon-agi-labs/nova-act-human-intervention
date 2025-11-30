# Amazon Nova Act Human Intervention Service

Backend service for Human-in-the-Loop (HITL) interventions in Nova Act workflows. Provides Step Functions-based patterns for Approval and UI Takeover use cases, enabling human decision-making and interaction within automated agent flows.

## Overview

This package implements AWS Lambda functions that power two types of human intervention patterns:

1. **Approval Pattern**: Request human approval for specific actions (e.g., financial transactions, sensitive operations)
2. **UI Takeover Pattern**: Request human interaction for complex UI tasks (e.g., CAPTCHAs, form filling, account verification)

## Architecture

The service consists of:
- **Step Functions Patterns**: State machines orchestrating intervention logic
- **Lambda Handlers**: Process intervention requests, generate SPAs, check completion status
- **WebSocket API**: Real-time communication with client executors
- **DynamoDB**: Store execution state and user responses
- **CloudFront + S3**: Host and serve Single Page Applications (SPAs) to users

## External Service Configuration

The HITL service integrates with external notification services that **must be configured separately**. These configurations are **out of scope** for the HITL service deployment and require manual setup.

### Slack Notification Setup

To enable Slack notifications, you must:

1. **Create a Slack Workflow** (out of scope for HITL service):
   - Go to your Slack workspace
   - Create a new Workflow with a webhook trigger
   - Configure the workflow to post messages to your desired channel
   - Copy the webhook URL

2. **Update AWS Secrets Manager**:
   - Locate the secret used by the HITL service for notification configuration
   - Update the `SlackWebhookURL` field with your Slack webhook URL:
     ```json
     {
       "SlackWebhookURL": "https://hooks.slack.com/workflows/YOUR_WEBHOOK_URL"
     }
     ```

3. **Use Slack notification channel**:
   - When creating intervention requests, specify `NotificationChannel.SLACK`:
     ```python
     NotificationRecipient(
         contact_info="your-channel-name",
         channel=NotificationChannel.SLACK
     )
     ```

**Note**: The HITL service does **not** create or manage Slack workflows (Slack's automation feature). You are responsible for creating and maintaining the Slack workflow in your workspace.

### Email Notification Setup

To enable email notifications, you must:

1. **Configure AWS SES** (out of scope for HITL service):
   - Verify your email domain or individual email addresses in AWS SES
   - For production use, move out of SES sandbox mode
   - Ensure the sender email address is verified in SES
   - Configure SPF/DKIM records for your domain (recommended for production)

2. **Verify sender identity**:
   - The default sender is configured in `email_notifier.py`
   - Ensure this email address is verified in SES in the deployment region

3. **Verify recipient addresses** (if in SES sandbox):
   - In sandbox mode, recipient email addresses must also be verified
   - Production mode allows sending to any email address

4. **Use email notification channel**:
   - When creating intervention requests, specify `NotificationChannel.EMAIL`:
     ```python
     NotificationRecipient(
         contact_info="user@example.com",
         channel=NotificationChannel.EMAIL
     )
     ```

**Note**: The HITL service does **not** configure AWS SES, verify domains, or manage email identities. You are responsible for all SES configuration and compliance with email sending policies.

### Configuration Verification

After configuring external services, test notifications:

```bash
# Test Slack notification
python -m nova_agent_human_intervention.test_notification --channel slack

# Test Email notification
python -m nova_agent_human_intervention.test_notification --channel email
```

If notifications fail, check:
- Slack webhook URL is correct and workflow is active
- SES sender/recipient addresses are verified
- Lambda execution role has permissions to access Secrets Manager and SES
- CloudWatch Logs for detailed error messages

## Approval Pattern

### Complete Flow

```
Client Side (Nova Act/Executor):
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Nova Act executes and needs human approval                       │
│ 2. Callbacks create ApprovalInterventionExecutor                    │
│ 3. Capture screenshot → Base64 data URL                             │
│ 4. Upload screenshot data URL to S3                                 │
│ 5. Connect to WebSocket (SigV4 signed URL)                          │
│ 6. Send ApprovalRequest:                                            │
│    • question: "Are you sure you want to proceed?"                  │
│    • options: [Approve, Deny]                                       │
│    • screenshot: S3 presigned URL                                   │
│    • notification_recipients: [email/slack]                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Backend Step Functions Workflow:
┌─────────────────────────────────────────────────────────────────────┐
│ [SPA Generation State]                                              │
│ ApprovalWorkflowHandler.handle_spa_generator()                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ 1. Download screenshot data URL from S3                         │ │
│ │ 2. Generate SPA HTML with:                                      │ │
│ │    • Embedded screenshot (data URL in <img> tag)                │ │
│ │    • Question display                                           │ │
│ │    • Clickable option buttons (Approve/Deny)                    │ │
│ │ 3. Upload SPA to CloudFront/S3                                  │ │
│ │ 4. Delete screenshot from S3 (cleanup)                          │ │
│ │ 5. Send notification (Email/Slack) with SPA URL                 │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ [Wait State - Polling Loop]                                         │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ BaseWorkflowHandler.handle_confirm_if_answered()                │ │
│ │ • Poll DynamoDB every 30 seconds                                │ │
│ │ • Check executionStatus field                                   │ │
│ │ • Return true if COMPLETED or TERMINATED                        │ │
│ │ • Continue loop until answered or timeout                       │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ [Completion State]                                                  │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ BaseWorkflowHandler.handle_completion()                         │ │
│ │ • Triggered by EventBridge on Step Functions completion         │ │
│ │ • Map Step Functions status → execution status                  │ │
│ │ • Update DynamoDB with final status                             │ │
│ │ • Call _get_completion_message_fields() hook                    │ │
│ │   └─> ApprovalWorkflowHandler adds: approvalAction              │ │
│ │ • Send WebSocket message to client with result                  │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
User Interaction:
┌─────────────────────────────────────────────────────────────────────┐
│ 1. User receives notification (Email/Slack)                         │
│ 2. User opens SPA URL in browser                                    │
│ 3. User views screenshot + question                                 │
│ 4. User clicks "Approve" or "Deny" button                           │
│ 5. SPA JavaScript calls API Gateway endpoint                        │
│ 6. API updates DynamoDB:                                            │
│    • executionStatus → COMPLETED                                    │
│    • approvalAction → APPROVE or DENY                               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Client Side Response:
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Executor receives WebSocket message:                             │
│    {                                                                │
│      "type": "workflow_completed",                                  │
│      "executionStatus": "COMPLETED",                                │
│      "approvalAction": "APPROVE"                                    │
│    }                                                                │
│ 2. executor.run() returns                                           │
│ 3. NovaAct callbacks.approve() returns True/False                  │
│ 4. NovaAct continues execution based on approval decision          │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Components

- **ApprovalWorkflowHandler**: Handles Approval-specific logic (screenshot processing, approval options)
- **Screenshot Flow**: Upload → S3 → Embedded in SPA → Cleanup
- **Response**: Includes `approvalAction` field (APPROVE/DENY)

## UI Takeover Pattern

### Complete Flow

```
Client Side (Nova Act/Executor):
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Nova Act encounters complex UI (e.g., CAPTCHA)                   │
│ 2. Callbacks create UITakeoverInterventionExecutor                  │
│ 3. Connect to WebSocket (SigV4 signed URL)                          │
│ 4. Send UITakeoverRequest:                                          │
│    • message: "Please complete the CAPTCHA"                         │
│    • browser_session_id: "01K8JZN717V0X8MXM0MT3ESBR4"               │
│    • notification_recipients: [email/slack]                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Backend Step Functions Workflow:
┌─────────────────────────────────────────────────────────────────────┐
│ [SPA Generation State]                                              │
│ UITakeoverWorkflowHandler.handle_spa_generator()                    │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ 1. Generate SPA HTML with:                                      │ │
│ │    • Message display                                            │ │
│ │    • Embedded browser interface (iframe to remote session)      │ │
│ │    • Submit completion button                                   │ │
│ │ 2. Upload SPA to CloudFront/S3                                  │ │
│ │ 3. Send notification (Email/Slack) with SPA URL                 │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ [Wait State - Polling Loop]                                         │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ BaseWorkflowHandler.handle_confirm_if_answered()                │ │
│ │ • Poll DynamoDB every 30 seconds                                │ │
│ │ • Check executionStatus field                                   │ │
│ │ • Return true if COMPLETED or TERMINATED                        │ │
│ │ • Continue loop until answered or timeout                       │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│ [Completion State]                                                  │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ BaseWorkflowHandler.handle_completion()                         │ │
│ │ • Triggered by EventBridge on Step Functions completion         │ │
│ │ • Map Step Functions status → execution status                  │ │
│ │ • Update DynamoDB with final status                             │ │
│ │ • Call _get_completion_message_fields() hook                    │ │
│ │   └─> UITakeoverWorkflowHandler uses default (no extra fields)  │ │
│ │ • Send WebSocket message to client with result                  │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
User Interaction:
┌─────────────────────────────────────────────────────────────────────┐
│ 1. User receives notification (Email/Slack)                         │
│ 2. User opens SPA URL in browser                                    │
│ 3. User views message + embedded browser interface                  │
│ 4. User interacts with browser:                                     │
│    • Solve CAPTCHA                                                  │
│    • Fill forms                                                     │
│    • Complete verification                                          │
│ 5. User clicks "Submit Completion" button                           │
│ 6. SPA JavaScript calls API Gateway endpoint                        │
│ 7. API updates DynamoDB:                                            │
│    • executionStatus → COMPLETED                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
Client Side Response:
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Executor receives WebSocket message:                             │
│    {                                                                │
│      "type": "workflow_completed",                                  │
│      "executionStatus": "COMPLETED"                                 │
│    }                                                                │
│ 2. executor.run() returns                                           │
│ 3. NovaAct callbacks.ui_takeover() returns                         │
│ 4. NovaAct continues with browser in updated state                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Components

- **UITakeoverWorkflowHandler**: Handles UI Takeover-specific logic (browser session management)
- **Browser Interface**: Remote browser session embedded in SPA iframe
- **Response**: Simple completion notification (no additional fields)

## Code Architecture

### Handler Hierarchy

```
BaseWorkflowHandler (Abstract Base Class)
├─ __init__(): Initialize AWS resources (boto3, S3, DynamoDB, NotificationFactory)
├─ handle_confirm_if_answered(): Poll DynamoDB for completion status
├─ handle_completion(): Process EventBridge events, send WebSocket notifications
├─ _get_completion_message_fields(): Hook for workflow-specific fields (default: {})
└─ handle_spa_generator(): Abstract method for workflow-specific SPA generation

           ┌──────────────────────────┴──────────────────────────┐
           │                                                     │
           ▼                                                     ▼
ApprovalWorkflowHandler                         UITakeoverWorkflowHandler
├─ __init__():                                  (uses base __init__)
│  └─ Add S3PresignedUrlHandler
├─ handle_spa_generator():                      ├─ handle_spa_generator():
│  └─ Generate Approval SPA                     │  └─ Generate UI Takeover SPA
└─ _get_completion_message_fields():            └─ (uses default hook)
   └─ Return {"approvalAction": "APPROVE/DENY"}
```

### Shared Logic (Base Class)

All common workflow operations are implemented in `BaseWorkflowHandler`:

1. **Resource Initialization**: boto3 session, S3 client, DynamoDB resource
2. **Status Checking**: Poll DynamoDB for COMPLETED/TERMINATED status
3. **Completion Handling**: Process EventBridge events, update DynamoDB, send WebSocket messages
4. **Error Handling**: Consistent logging and exception management

### Workflow-Specific Logic (Subclasses)

Each workflow handler implements only its unique requirements:

- **ApprovalWorkflowHandler**: Screenshot processing, approval options, S3 presigned URLs
- **UITakeoverWorkflowHandler**: Browser session management, remote control interface

## Integration with Nova Act SDK

Nova Act integrates with this service through the `amzn_nova_act_human_intervention_client` package:

```python
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    UITakeoverInterventionExecutor,
    AssumedRoleCredentialsProvider
)

# In Nova Act SDK callbacks
class NovaActHumanInputCallbacks(HumanInputCallbacksBase):
    def approve(self, message: str) -> bool:
        """Request human approval"""
        executor = ApprovalInterventionExecutor(...)
        executor.run(ApprovalRequest(...))
        return executor.completion_response["approvalAction"] == "APPROVE"

    def ui_takeover(self, message: str) -> None:
        """Request human UI interaction"""
        executor = UITakeoverInterventionExecutor(...)
        executor.run(UITakeoverRequest(...))

# Usage in Nova Act SDK
with NovaAct(human_input_callbacks=callbacks) as nova:
    nova.act("Book a restaurant, ask for approval before confirming")
```

See `amzn_nova_act_human_intervention_client/test_examples/` for complete examples.

## Development

### Unit Tests

Run unit tests:
```bash
hatch test
```

### Type Checking

Run type checking:
```bash
hatch run typing
```

### Update Dependencies

Update lock files:
```bash
hatch run update
```

## Deployment

This package is deployed via the CDK package. See CDK package documentation for deployment instructions.

## Project Structure

```
src/nova_agent_human_intervention/
├── workflows/
│   ├── base_handlers.py           # BaseWorkflowHandler, BaseApiHandler
│   ├── approval/
│   │   ├── sfn/handlers.py        # ApprovalWorkflowHandler
│   │   └── api/handlers.py        # Approval API endpoints
│   └── ui_takeover/
│       ├── sfn/handlers.py        # UITakeoverWorkflowHandler
│       └── api/handlers.py        # UI Takeover API endpoints
├── executors/
│   ├── websocket/                 # WebSocket connection handlers
│   └── streams/                   # DynamoDB Streams handlers
├── notifications/                 # Email/Slack notification senders
└── utils/                         # Shared utilities

tests/                             # Unit tests mirroring src/ structure
```
