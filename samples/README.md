# Amazon Nova Act Human Intervention Service Examples

This folder contains example implementations demonstrating how to integrate Nova Act with the Human Intervention Service for human-in-the-loop patterns.

## Overview

These examples show how to use the Nova Act Human Intervention Client SDK to implement two primary use cases:

1. **Approval**: Request human approval for specific actions (e.g., financial transactions, sensitive operations)
2. **UI Takeover**: Request human intervention for complex UI interactions (e.g., CAPTCHAs, complex forms)

## Examples

### 1. standalone-hitl-run.py

A standalone example demonstrating direct usage of the intervention executors without Nova Act integration. This example shows:

- How to set up credentials providers for IAM role assumption
- How to create and execute Approval patterns with screenshot uploads
- How to create and execute UI Takeover patterns with browser session sharing
- How to handle pattern completion and responses

**Use this example when:**
- You want to understand the core HITL client SDK functionality
- You need to integrate human intervention into non-Nova Act automations
- You want to test the HITL service independently

### 2. nova-act-integration.py

A complete Nova Act integration example that implements the `HumanInputCallbacksBase` interface. This example shows:

- How to create a custom `HumanInputCallbacks` implementation
- How to integrate HITL patterns into Nova Act automation
- How to handle approval requests during Nova Act execution
- How to hand over browser control to humans during complex interactions

**Use this example when:**
- You're building Nova Act automations that require human input
- You need to implement approval gates in automated processes
- You want to handle CAPTCHAs or other challenges requiring human intervention

## Prerequisites

Before running these examples, ensure you have:

1. **AWS Credentials**: Configured via environment variables, `~/.aws/credentials`, or IAM role
2. **IAM Permissions**:
   - It is easier to run patterns as an **AWS Administrator**
   - If you cannot use admin privileges, attach the `NovaAct-HITL-AssumeExecutionRole-<disambiguator>` managed policy to your IAM role/user (see main README deployment section)
   - This policy grants: `sts:AssumeRole` permission for the executor IAM role, which provides `execute-api:ManageConnections`, `execute-api:Invoke`, and `s3:PutObject` (for screenshots)
3. **Python Dependencies**: Install the required packages:
   ```bash
   pip install amzn-nova-act-human-intervention-client
   pip install amzn-nova-act-human-intervention-common
   pip install nova-act  # For nova-act-integration.py
   pip install bedrock-agentcore  # For browser session support
   pip install boto3 click pillow
   ```

4. **Infrastructure**: Deploy the Human Intervention service infrastructure (see main README)

## Configuration

Both examples use environment variables for configuration:

```bash
export AWS_REGION="us-east-1"
export HITL_EXECUTOR_ENDPOINT="wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod"
export HITL_EXECUTION_TIMEOUT="7200"
export HITL_IAM_ROLE_ARN="arn:aws:iam::123456789012:role/YourExecutionRole"
export HITL_SCREENSHOT_S3_BUCKET="your-screenshot-bucket"
```

Or pass them as command-line arguments (see examples below).

## Usage

### Standalone Example - Approval Use Case

```bash
# Using environment variables
AWS_PROFILE=your-profile python standalone-hitl-run.py --use-case Approval

# Using command-line arguments
AWS_PROFILE=your-profile python standalone-hitl-run.py \
    --aws-region us-east-1 \
    --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
    --execution-timeout 7200 \
    --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
    --screenshot-s3-bucket your-screenshot-bucket \
    --use-case Approval
```

### Standalone Example - UI Takeover Use Case

```bash
AWS_PROFILE=your-profile python standalone-hitl-run.py \
    --aws-region us-east-1 \
    --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
    --execution-timeout 7200 \
    --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
    --screenshot-s3-bucket your-screenshot-bucket \
    --use-case UITakeover
```

### Nova Act Integration Example

```bash
# Approval pattern
AWS_PROFILE=your-profile python nova-act-integration.py \
    --aws-region us-east-1 \
    --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
    --execution-timeout 7200 \
    --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
    --screenshot-s3-bucket your-screenshot-bucket \
    --use-case Approval

# UI Takeover pattern
AWS_PROFILE=your-profile python nova-act-integration.py \
    --aws-region us-east-1 \
    --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
    --execution-timeout 7200 \
    --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
    --screenshot-s3-bucket your-screenshot-bucket \
    --use-case UITakeover
```

## How It Works

### Approval Pattern

1. The client captures a screenshot of the current browser state
2. Screenshot is converted to a Base64 data URL and uploaded to S3
3. Client connects to WebSocket API using SigV4 authentication
4. Client sends an approval request with the screenshot reference
5. Backend downloads the screenshot and generates a Single Page Application (SPA)
6. User receives notification (email/Slack) with link to SPA
7. User reviews the screenshot and selects an option (Approve/Deny)
8. Client receives the decision via WebSocket
9. Automation continues based on the user's decision

### UI Takeover Pattern

1. Client connects to WebSocket API using SigV4 authentication
2. Client sends a UI takeover request with browser session ID
3. Backend generates an SPA with embedded browser interface
4. User receives notification (email/Slack) with link to SPA
5. User takes control of the browser session through the SPA
6. User completes the required task (e.g., solves CAPTCHA)
7. User submits completion through the SPA
8. Client receives completion message via WebSocket
9. Automation resumes with updated browser state

## Customization

### Notification Recipients

Both examples use email notifications by default. You can customize the notification recipients:

```python
from amzn_nova_act_human_intervention_common import (
    NotificationRecipient,
    EmailContactInfo,
    SlackContactInfo,
    SlackTargetType,
)

# Email notification
NotificationRecipient(
    contact_info=EmailContactInfo(
        to_email_address="user@example.com",
        from_email_address="noreply@example.com",
    )
)

# Slack notification
NotificationRecipient(
    contact_info=SlackContactInfo(
        channel="#your-channel",
        target="@username",  # or user ID
        target_type=SlackTargetType.USER,
    )
)
```

### Approval Options

Customize approval options to fit your use case:

```python
from amzn_nova_act_human_intervention_common import ApprovalOption, ApprovalAction

options = [
    ApprovalOption(label="Approve Transaction", action=ApprovalAction.APPROVE),
    ApprovalOption(label="Reject Transaction", action=ApprovalAction.DENY),
    ApprovalOption(label="Escalate to Manager", action=ApprovalAction.DENY),
]
```

### Timeout Configuration

Adjust the execution timeout based on your requirements:

- Short timeouts (< 1 hour): For quick approvals or UI interactions
- Medium timeouts (1-4 hours): For standard business processes
- Long timeouts (4-8 hours): For processes spanning work shifts

**Note**: The IAM role session duration must be >= execution timeout.

## Troubleshooting

### Connection Issues

If you encounter WebSocket connection errors:

1. Verify the executor endpoint URL is correct
2. Check that IAM role has `execute-api:Invoke` permissions
3. Ensure the WebSocket API Gateway is deployed and accessible
4. Verify AWS credentials are valid and not expired

### Screenshot Upload Failures

If screenshot uploads fail:

1. Check IAM role has `s3:PutObject` permission for the bucket
2. Verify the S3 bucket exists and is in the same region
3. Ensure the bucket has appropriate CORS configuration (if applicable)

### Timeout Errors

If patterns timeout:

1. Increase `--execution-timeout` value
2. Ensure IAM role session duration >= execution timeout
3. Check that notifications are being delivered to recipients
4. Verify the SPA URL is accessible to users

### Import Errors

If you see import errors:

```bash
pip install amzn-nova-act-human-intervention-client
pip install amzn-nova-act-human-intervention-common
pip install nova-act  # For Nova Act integration
pip install bedrock-agentcore  # For browser sessions
```

## Security Best Practices

1. **Never hardcode credentials**: Use environment variables or IAM roles
2. **Use least privilege**: Grant only necessary IAM permissions
3. **Rotate credentials**: Regularly rotate IAM role credentials
4. **Secure notifications**: Use verified email addresses and private Slack channels
5. **Monitor access**: Enable CloudWatch logging for WebSocket API and S3 bucket
6. **Review screenshots**: Ensure screenshots don't contain sensitive data before approval

## Learn More

- [Nova Act Documentation](https://nova.amazon.com/act)
- [Main Project README](../README.md)
- [SDK Documentation](../sdk/README.md)

## Support

For issues, questions, or contributions, please refer to the main project repository.
