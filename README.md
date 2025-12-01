# Amazon Nova Act Human Intervention Service

## About This Project

This project contains a reference implementation of an end-to-end human intervention service to enable Nova Act human-in-the-loop (HITL) patterns on AWS complete with a notifications system and single page app to manage human in the loop patterns.

> ℹ️ **New to Nova Act and HITL patterns?** We recommend starting with a [basic example](https://github.com/amazon-agi-labs/nova-act-samples/examples/human_in_the_loop) and checking out the [Amazon Nova Act HITL documentation](https://github.com/amazon-agi-labs/nova-act-samples/examples/human_in_the_loop/README.md) before continuing.

## About Amazon Nova Act

Amazon Nova Act is available as an AWS service to build and manage fleets of reliable AI agents for automating production UI workflows at scale. Nova Act completes repetitive UI workflows in the browser and escalates to a human supervisor when appropriate. You can define workflows by combining the flexibility of natural language with Python code. Start by exploring in the web playground at [nova.amazon.com/act](https://nova.amazon.com/act), develop and debug in your IDE, deploy to AWS, and monitor your workflows in the AWS Console, all in just a few steps.

(Preview) Nova Act also integrates with external tools through API calls, remote MCP, or agentic frameworks, such as Strands Agents.

## Overview

This project provides a complete solution for implementing human intervention patterns with Nova Act. It includes:

- **Python SDK**: Client library for integrating HITL patterns into your applications
- **AWS CDK Infrastructure**: Reusable constructs for deploying the service to AWS
- **Two Intervention Types**:
  1. **Approval**: Request human approval before completing automated actions. Useful for:
     - Confirming expense and purchase approvals
     - Validating data before submission
  2. **UI Takeover**: Pause automation to let humans handle complex interactions. Useful for:
     - Solving CAPTCHAs
     - Handling login/authentication flows

**Key Components:**
- **AWS Infrastructure** (`cdk/`) - Deploy WebSocket API, Step Functions, and SPA hosting to power your HITL patterns
- **Lambda Handlers** (`sdk/service/`) - Backend service implementation to interact with the service
- **Python Client SDK** (`sdk/client/`) - Connect to the service from your applications
- **Sample Integrations** (`samples/`) - Ready-to-run examples with the Nova Act SDK

## Key Concepts

Understanding these core technologies will help you work with the Human Intervention Service:

- **Single Page Application (SPA)**: A self-contained HTML file that runs entirely in the browser. When a human intervention is needed, the service generates a custom SPA containing all necessary code, styling, and data embedded directly in the HTML. Users receive a link, open it in any browser, and can interact immediately without installing software. The SPA is hosted on S3 and served globally via CloudFront.

- **WebSocket**: A persistent, bidirectional communication channel between the client SDK and AWS. Unlike regular HTTP requests that close after each response, WebSocket connections stay open, allowing the backend to instantly notify the client when a user completes an intervention. This enables the client SDK to wait (block) until the human responds.

- **Step Functions**: AWS's serverless workflow orchestration service. In this application, Step Functions coordinate the entire intervention lifecycle: storing metadata, generating the SPA, polling for user responses every 30 seconds, and triggering cleanup after completion. It provides built-in retry logic, timeout handling, and visual workflow monitoring.

- **S3 (Simple Storage Service)**: AWS's object storage service used for two purposes in this application. First, it temporarily stores screenshots uploaded by the client SDK during approval patterns (encrypted with KMS, automatically deleted after 1 day). Second, it hosts the generated SPA HTML files that are served to users via CloudFront. Both use cases leverage S3's durability and integration with other AWS services.

- **DynamoDB**: A NoSQL database that stores intervention execution state. Each pattern instance is tracked with atomic updates to prevent duplicate submissions and Time-To-Live (TTL) attributes for automatic cleanup after 24 hours. DynamoDB Streams trigger Lambda functions when records expire, enabling immediate S3 cleanup.

- **Amazon DCV (Desktop Cloud Visualization)**: A high-performance remote display protocol for secure browser streaming, formerly known as NICE DCV. The [Amazon DCV Web Client SDK](https://docs.aws.amazon.com/dcv/latest/websdkguide/what-is.html) is a JavaScript library that enables real-time remote desktop and application streaming directly in web browsers. In the UI Takeover pattern, DCV streams the live browser session from Amazon Bedrock AgentCore to the human operator's browser, transmitting only encrypted pixels (not data) over WebSocket connections. The SDK supports mouse, keyboard, and touch input, allowing users to interact with the remote browser as if it were running locally.

## Quick Start

### 1. Set Up Python SDK (Development)

If you're developing or testing the SDK locally:

```bash
# Navigate to SDK directory
cd sdk

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install packages in dependency order
pip install ./common
pip install ./service
pip install ./client

# (Optional) Run tests and build
pip install hatch
./build-and-test.sh
```

See [sdk/README.md](sdk/README.md) for detailed SDK documentation.

### 2. Build Lambda Assets for CDK Deployment

Before deploying the infrastructure, build the Lambda packages:

```bash
# Navigate to lambda build directory
cd cdk/lambda-assets-build

# Build Lambda deployment packages
./build-lambda-packages.sh
```

This script:
- Installs dependencies from `requirements-service.txt` and `requirements-common.txt`
- Copies source code from `sdk/service/` and `sdk/common/`
- Creates deployment packages in `cdk/lambda-packages/handlers/`

### 3. Deploy CDK Infrastructure

Deploy the AWS infrastructure using the CDK deployment script:

```bash
# Navigate to CDK directory
cd cdk

# Configure environment (choose stage name and region)
export DEPLOYMENT_STAGE="dev"           # dev, staging, or prod
export DEPLOYMENT_REGION="us-east-1"    # Target AWS region
export STACK_DISAMBIGUATOR="dev"        # Unique identifier

# First-time AWS user? Run the setup wizard
./setup-and-deploy.sh first-time-setup

# Already have AWS credentials? Deploy directly
./setup-and-deploy.sh prepare      # Install dependencies, build, synthesize
./setup-and-deploy.sh bootstrap    # First time only
./setup-and-deploy.sh deploy       # Deploy all stacks

# Or use the quick deploy command
./setup-and-deploy.sh quick-deploy
```

**IAM Permissions for Running Patterns:**

It is easier to run patterns as an **AWS Administrator**. If you cannot use admin privileges, attach the managed policy created by the deployment to your IAM role/user:

```bash
# Get the policy ARN from deployment outputs
./setup-and-deploy.sh outputs | grep AssumeExecutionRolePolicyArn

# Attach to your IAM user or role
aws iam attach-user-policy \
  --user-name <your-username> \
  --policy-arn arn:aws:iam::<account-id>:policy/NovaAct-HITL-AssumeExecutionRole-<disambiguator>

# Or for a role:
aws iam attach-role-policy \
  --role-name <your-role-name> \
  --policy-arn arn:aws:iam::<account-id>:policy/NovaAct-HITL-AssumeExecutionRole-<disambiguator>
```

This policy grants permission to assume the execution role (`NovaAct-HITL-ExecutionRole-*`) which is required to run the human intervention patterns. See `cdk/lib/executors/websocketExecutorStack.ts` (line 410) for the policy definition.

See [cdk/README.md](cdk/README.md) for detailed CDK deployment documentation.

### 4. Try the Examples

Run the sample integrations to test your deployment:

```bash
cd samples

# Set up environment variables with your deployed stack outputs
export AWS_REGION="<region you have deployed the service to>"
export HITL_EXECUTOR_ENDPOINT="wss://<your-api-id>.execute-api.<region>.amazonaws.com/prod"
export HITL_EXECUTION_TIMEOUT="7200"
export HITL_IAM_ROLE_ARN="arn:aws:iam::<account-id>:role/<your-role-name>"
export HITL_SCREENSHOT_S3_BUCKET="<your-screenshot-bucket>"

# Run standalone HITL examples (Approval pattern)
python standalone-hitl-run.py --use-case Approval

# Run standalone HITL examples (UI Takeover pattern)
python standalone-hitl-run.py --use-case UITakeover

# Run full Nova Act integration example
python nova-act-integration.py --use-case Approval
```

Or use command-line arguments instead of environment variables:

```bash
# Using command-line arguments
python standalone-hitl-run.py \
    --aws-region <region> \
    --executor-endpoint wss://<your-api-id>.execute-api.<region>.amazonaws.com/prod \
    --execution-timeout 7200 \
    --executor-iam-role-arn arn:aws:iam::<account-id>:role/<your-role-name> \
    --screenshot-s3-bucket <your-screenshot-bucket> \
    --use-case Approval
```

See [samples/README.md](samples/README.md) for detailed usage examples.

### 5. Configure Notification Channels

The service supports **Email (AWS SES)** and **Slack** notifications to alert users when human intervention is needed.

#### Email Setup (AWS SES)

1. **Verify sender email address:**

```bash
aws ses verify-email-identity \
  --email-address noreply@yourdomain.com \
  --region <region you have deployed the service to>
```

2. **Check verification email** sent to the address and click the verification link

3. **(Optional) Request production access:**
   - By default, SES is in sandbox mode (can only send to verified addresses)
   - To send to any email address, request production access in the AWS SES Console

4. **(Optional) Verify your domain** for DKIM signing and better deliverability

**Usage in client code:**

```python
from amzn_nova_act_human_intervention_common import (
    NotificationRecipient,
    EmailContactInfo,
)

notification_recipients=[
    NotificationRecipient(
        contact_info=EmailContactInfo(
            to_email_address="user@example.com",
            from_email_address="noreply@yourdomain.com"  # Must be verified in SES
        )
    )
]
```

#### Slack Setup

1. **Create a Slack App** using the provided manifest (recommended):
   - Go to [api.slack.com/apps](https://api.slack.com/apps) → "Create New App" → **"From an app manifest"**
   - Select your workspace
   - Paste the manifest from `cdk/slack-app-manifests/Approval.json` or `cdk/slack-app-manifests/UITakeover.json`
   - Review and create the app

2. **Install the app to your workspace:**
   - Click "Install to Workspace"
   - Authorize the app
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`)

3. **Store the token in AWS Secrets Manager:**

```bash
# Get the secret name from your deployment outputs
cd cdk
./setup-and-deploy.sh outputs | grep -i slack

# Update the secret with your bot tokens
# Secret name pattern: nova-act-slack-secrets-{your-disambiguator}
aws secretsmanager update-secret \
  --secret-id "nova-act-slack-secrets-dev" \
  --secret-string '{"UITakeover":"xoxb-your-token","Approval":"xoxb-your-token"}' \
  --region <region you have deployed the service to>
```

**Usage in client code:**

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
            channel="#general",  # Channel ID or name
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
```

**Getting Slack Channel IDs:**
- Right-click on a channel → "View channel details" → Copy the Channel ID
- Or use the channel name with `#` prefix (e.g., `#general`)

See [cdk/README.md#notifications-setup](cdk/README.md#notifications-setup) for detailed configuration and [samples/README.md#notification-recipients](samples/README.md#notification-recipients) for usage examples.

## Human Intervention Patterns

Nova Act is previewing the ability to integrate external tools beyond the browser, such as an API Call or Database Query, into workflows. This functionality enables developers to integrate remote MCP tools and agentic frameworks, such as Strands Agents, into their workflows.

Nova Act automatically detects scenarios where human intervention is required during workflow execution. When Nova Act encounters tasks it cannot complete autonomously—such as CAPTCHAs, complex decision points, or ambiguous UI elements—it can invoke human-in-the-loop (HITL) tools to request assistance.

The Nova Act SDK provides HITL tools that can be invoked through callbacks, allowing you to seamlessly integrate human intervention into your automation without interrupting the overall workflow. These tools enable you to specify when and how human assistance should be requested. Learn more in the [Nova Act SDK documentation](https://github.com/aws/nova-act).

The following sections describe how the service implemented in this repository handles each pattern type, including their architecture, use cases, and implementation details. 

### Approval Pattern

#### What is it?

The Approval pattern enables asynchronous human decision-making in automated processes. When Nova Act encounters a decision point requiring human judgment, it captures a screenshot of the current state and presents it to a human reviewer via a browser-based Single Page Application (SPA).

#### When to use it?

Use the Approval pattern when you need:
- **Binary or multi-choice decisions**: Approve/Reject, Yes/No, or selecting from predefined options
- **Asynchronous review**: The human can respond from any device, at any time within the timeout period
- **Context via screenshot**: Visual representation of the current state is sufficient for decision-making
- **Audit trail**: Every decision is recorded in DynamoDB with timestamps and user actions

**Common Use Cases:**
- Confirming expense and purchase approvals
- Validating data before submission

#### High-Level Flow

1. **Request Initiation**: The client SDK creates an approval request with:
   - A screenshot of the current browser state
   - A question or prompt for the human
   - Predefined response options (e.g., "Approve", "Deny")
   - Notification recipients (email addresses, Slack channels)

2. **Workflow Orchestration**: The request triggers an AWS Step Functions workflow that:
   - Stores execution metadata in DynamoDB
   - Uploads the screenshot to S3 (KMS encrypted, 1-day lifecycle)

3. **SPA Generation**: A Lambda function generates a custom HTML page containing:
   - The embedded screenshot (converted from S3 URL to base64 data URL)
   - The question and response buttons
   - API endpoints for submitting decisions and checking status
   - JavaScript for real-time status polling

4. **Notification Delivery**: The system sends notifications via:
   - **Email** (Amazon SES): Direct link to the approval SPA
   - **Slack** (optional): Threaded message with link

5. **Human Interaction**: The user opens the SPA in their browser and:
   - Views the screenshot and question
   - Clicks "Approve" or "Deny" (or custom action)
   - Confirms the decision (optional confirmation dialog for destructive actions)

6. **Decision Recording**: The SPA calls a REST API that:
   - Atomically updates DynamoDB with the decision (preventing duplicate submissions)
   - Sends a confirmation notification (threaded in Slack)
   - Returns success to the browser

7. **Polling & Detection**: The Step Function polls every 30 seconds to check if the decision has been recorded in DynamoDB

8. **Completion**: When a decision is detected:
   - EventBridge emits a completion event
   - A completion handler Lambda sends the result via WebSocket back to the waiting client SDK
   - The SDK returns the decision to the calling code

9. **Cleanup**: After the TTL expires (24 hours default):
   - DynamoDB automatically deletes the execution record
   - DynamoDB Streams trigger a cleanup Lambda
   - The Lambda deletes the SPA HTML from S3 (sub-minute cleanup)

#### Key Architectural Components

- **WebSocket API Gateway**: Maintains persistent connection between client SDK and AWS
- **REST API Gateway**: Handles SPA user interactions with custom token-based authentication
- **Step Functions**: Orchestrates the workflow with 30-second polling and 24-hour timeout
- **DynamoDB**: Stores execution state with atomic conditional updates and TTL-based expiration
- **S3 + CloudFront**: Hosts SPA with global CDN delivery and custom error pages
- **Lambda Functions**: 11 functions handling WebSocket, REST API, pattern tasks, and cleanup
- **EventBridge**: Triggers completion handlers on Step Function status changes
- **DynamoDB Streams**: Enables immediate S3 cleanup on TTL expiration

#### Architecture Diagram

![Approval Pattern Architecture](Approval%20High-Level%20Flow.svg)

---

### UI Takeover Pattern

#### What is it?

The UI Takeover pattern enables real-time human control of a remote browser session. When an Nova Act encounters a task that requires human interaction (like solving a CAPTCHA or navigating complex forms), it hands control of the browser to a human operator via a live-streaming interface.

#### When to use it?

Use the UI Takeover pattern when you need:
- **Real-time browser interaction**: The human must directly control the browser with mouse and keyboard
- **Interactive tasks**: Multi-step processes that can't be captured in a static screenshot
- **Live feedback**: The human needs to see real-time updates as they interact
- **Complex UI navigation**: Tasks like form filling and CAPTCHA solving

**Common Use Cases:**
- Solving CAPTCHAs
- Handling login/authentication flows

#### High-Level Flow

1. **Request Initiation**: The client SDK creates a UI takeover request with:
   - The browser session ID from Amazon Bedrock AgentCore
   - A message explaining what the human needs to do
   - Notification recipients

2. **Workflow Orchestration**: The request triggers an AWS Step Functions workflow that:
   - Stores execution metadata in DynamoDB (including `remoteBrowserSessionId`)
   - Links the pattern to an active browser session managed by Bedrock AgentCore

3. **SPA Generation**: A Lambda function generates a custom HTML page containing:
   - DCV (NICE DCV) streaming library integration
   - API endpoints for fetching browser session info and completing the task
   - JavaScript for establishing WebSocket connection to the browser stream
   - Picture-in-Picture support via DCV SDK
   - Real-time status polling

4. **Notification Delivery**: The system sends notifications via:
   - **Email** (Amazon SES): Direct link to the UI takeover SPA
   - **Slack** (optional): Threaded message with link

5. **Browser Session Connection**: When the user opens the SPA:
   - JavaScript calls the `/browser-session-info` API endpoint
   - The API queries Bedrock AgentCore for browser session status
   - AgentCore generates a presigned DCV streaming WebSocket URL
       - The URL is valis for 5 minutes but once you start streaming it should continue until there is a connection drop
       - The UI Takeover SPA, requests a new pre-signed URL when you refresh the page
   - The SPA receives the URL and browser viewport details

6. **Live Streaming**: The DCV SDK establishes a WebSocket connection to the browser:
   - Real-time video streaming of the browser screen
   - Mouse movements and clicks are transmitted to the remote browser
   - Keyboard input is captured and sent to the browser
   - Display scaling adjusts to the user's screen size

7. **Human Interaction**: The user controls the remote browser:
   - Clicks "Take over" to activate browser controls
   - Interacts with the browser (solve CAPTCHA, complete forms, etc.)
   - Sees live feedback of their actions
   - Optionally opens Picture-in-Picture window for multitasking

8. **Task Completion**: When finished:
   - User clicks "Complete task" button
   - SPA calls the `/complete-task` API endpoint
   - API atomically updates DynamoDB to mark the task as completed
   - Sends confirmation notification

9. **Polling & Detection**: The Step Function polls every 30 seconds to check if the task has been completed

10. **Completion**: When completion is detected:
    - EventBridge emits a completion event
    - Completion handler sends result via WebSocket to the client SDK
    - The SDK returns control to the calling code
    - **Note**: The browser session itself is managed separately by Bedrock AgentCore and is NOT terminated by this pattern

11. **Cleanup**: After TTL expires (24 hours default):
    - DynamoDB deletes the execution record
    - DynamoDB Streams trigger cleanup Lambda
    - Lambda deletes the SPA HTML from S3

#### Key Architectural Components

- **WebSocket API Gateway**: Maintains persistent connection between client SDK and AWS
- **REST API Gateway**: Handles SPA interactions including browser session info retrieval
- **Step Functions**: Orchestrates the workflow with 30-second polling and 24-hour timeout
- **DynamoDB**: Stores execution state with `remoteBrowserSessionId` linking to AgentCore
- **S3 + CloudFront**: Hosts SPA with embedded DCV streaming library
- **Lambda Functions**: 11 functions for WebSocket, REST API, browser session integration, and cleanup
- **Amazon Bedrock AgentCore**: Manages remote browser sessions and DCV streaming URLs
- **DCV (NICE DCV)**: Browser-based remote desktop protocol for live browser streaming
- **EventBridge**: Triggers completion handlers on workflow status changes
- **DynamoDB Streams**: Enables immediate S3 cleanup on TTL expiration

#### Browser Session Management

Unlike the Approval pattern, UI Takeover integrates with **Amazon Bedrock AgentCore** for browser session management:

- **Browser Sessions**: Created and managed by AgentCore independently of the HITL pattern
- **DCV Streaming**: AgentCore generates presigned WebSocket URLs for secure streaming access
- **Session Lifecycle**: Browser sessions persist beyond the HITL pattern completion
- **Picture-in-Picture**: Native DCV SDK support allows users to float the browser in an always-on-top window

**Important**: The UI Takeover pattern does NOT start or stop browser sessions. It only provides the human interface to control an existing browser session. Browser lifecycle management is the responsibility of the calling application using Nova Act.

#### Architecture Diagram

![UI Takeover Pattern Architecture](UITakeover%20High-Level%20Flow.svg)

---

### Pattern Comparison

| Aspect | Approval Pattern | UI Takeover Pattern |
|--------|-------------------|----------------------|
| **Interaction Type** | Asynchronous decision-making | Synchronous browser control |
| **User Input** | Click button (Approve/Deny) | Mouse, keyboard, live interaction |
| **Visual Context** | Static screenshot (embedded as base64) | Live browser streaming (DCV WebSocket) |
| **Typical Duration** | Seconds to minutes | Minutes to hours |
| **Use Case** | Binary or multi-choice decisions | Complex interactive tasks |
| **Browser Integration** | Screenshot only (no browser access) | Full browser control via AgentCore |
| **Response Options** | Predefined (configured in request) | Free-form interaction |
| **Streaming Technology** | None (static HTML) | DCV (NICE DCV) protocol |
| **External Dependencies** | None (self-contained) | Amazon Bedrock AgentCore |

---

## Prerequisites

To use this project, you'll need:

- **Python 3.12+** - For SDK development and running examples
- **AWS Account** - For deploying the infrastructure

**For CDK Deployment:**
- **Node.js 18+** - Required for AWS CDK
- **AWS CLI** - For managing AWS credentials
- **npm** or **yarn** - Node package manager

## Package Structure

```
.
├── sdk/                                # Python SDK packages
│   ├── client/                         # Python client library
│   ├── service/                        # Service/handler code (used in Lambda)
│   ├── common/                         # Common utilities (shared by service & client)
│   ├── build-and-test.sh               # Build, test, and lint all SDK packages
│   └── README.md                       # SDK documentation
├── cdk/                                # AWS CDK infrastructure
│   ├── lambda-assets-build/            # Lambda build scripts
│   │   └── build-lambda-packages.sh   # Build Lambda packages from SDK source
│   ├── bin/                            # CDK app entry point
│   ├── lib/                            # CDK constructs (Storage, Step Functions, WebSocket)
│   ├── lambda-packages/                # Lambda deployment packages (generated)
│   ├── setup-and-deploy.sh             # Deployment wizard and CLI
│   ├── CLI-GUIDE.md                    # Comprehensive deployment guide
│   └── README.md                       # CDK-specific documentation
├── samples/                            # Usage examples with Nova Act
│   ├── standalone-hitl-run.py          # Standalone HITL executor examples
│   ├── nova-act-integration.py         # Full Nova Act integration example
│   ├── test_screenshot.png             # Sample screenshot for testing
│   └── README.md                       # Detailed usage documentation
└── README.md                           # This file (project overview)
```

**Notes:**
- `cdk/lambda-packages/` is generated locally during deployment and excluded from git
- SDK packages can be used independently without deploying the CDK infrastructure
- For CDK-specific documentation, see [cdk/README.md](cdk/README.md)
- For SDK development, see [sdk/README.md](sdk/README.md)

## Documentation

- **[samples/README.md](samples/README.md)** - Complete usage examples and integration guide
- **[sdk/README.md](sdk/README.md)** - Python SDK development and testing
  - [sdk/client/README.md](sdk/client/README.md) - Client library API reference
  - [sdk/service/README.md](sdk/service/README.md) - Service implementation details
- **[cdk/README.md](cdk/README.md)** - CDK infrastructure deployment guide
  - [cdk/CLI-GUIDE.md](cdk/CLI-GUIDE.md) - Comprehensive deployment script documentation

## Support

For issues or questions:

**SDK and Usage:**
- Check [samples/README.md](samples/README.md) for complete examples
- Review [sdk/README.md](sdk/README.md) for SDK development guidance

**CDK Deployment:**
- Check [cdk/README.md](cdk/README.md) for deployment troubleshooting
- Review CloudWatch Logs for Lambda functions
- Check CloudFormation stack events in AWS Console

## Additional Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Step Functions](https://docs.aws.amazon.com/step-functions/)
- [AWS API Gateway WebSocket APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api.html)
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/)
