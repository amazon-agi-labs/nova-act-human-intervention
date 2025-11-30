# Amazon Nova Act Human Intervention Service - CDK Infrastructure

> This is the CDK-specific README. For the main project overview and SDK documentation, see the [parent README](../README.md).

AWS CDK constructs for deploying a human intervention service to enable Nova Act human-in-the-loop (HITL) patterns with WebSocket API, Step Functions, and SPA generation.

## Overview

This CDK application provides infrastructure for implementing human intervention patterns in AWS. It includes:

- **Storage Stack**: DynamoDB tables and S3/CloudFront for SPA hosting
- **Approval Step Function Stack**: Human approval/rejection patterns
- **UI Takeover Step Function Stack**: Complex UI interactions (CAPTCHA, authentication, etc.)
- **WebSocket Executor Stack**: Real-time WebSocket API for browser connections

## Prerequisites

Before deploying this CDK application, ensure you have:

- **Node.js 18+** installed
- **AWS CLI** installed and configured
- **AWS Account** with appropriate permissions
- **npm** or **yarn** package manager
- **Python 3.12+** (if you need to rebuild Lambda packages)

## Lambda Packages

This CDK application includes pre-built Lambda deployment packages in the `lambda-packages/` directory. These contain:
- Python handler code (`amzn_nova_act_human_intervention`) - built from `../sdk/service/`
- Common utilities (`amzn_nova_act_human_intervention_common`) - built from `../sdk/common/`
- All required dependencies

If you modify the SDK source code in `../sdk/service/` or `../sdk/common/`, rebuild the Lambda packages using:

```bash
cd scripts
./rebuild-lambda.sh
```

## Quick Start

**Note:** All commands in this section should be run from this directory (`cdk/`).

### Option 1: Using the Deployment Script (Recommended)

**🎓 First-time AWS user?**

```bash
./setup-and-deploy.sh first-time-setup
```

This interactive wizard will guide you through:
- Creating AWS credentials
- Configuring your environment
- Deploying the stacks

**Already have AWS credentials?**

```bash
# Check your credentials
./setup-and-deploy.sh check-credentials

# Use interactive mode (shows menu with all options)
./setup-and-deploy.sh -i

# OR deploy directly
./setup-and-deploy.sh prepare      # Install dependencies, build, synthesize
./setup-and-deploy.sh bootstrap    # First time only
./setup-and-deploy.sh deploy       # Deploy all stacks
```

**Quick deployment:**

```bash
./setup-and-deploy.sh quick-deploy
```

### Option 2: Using CDK Commands Directly

**1. Configure Environment Variables**

```bash
export AWS_PROFILE="hitl-deployer"            # AWS CLI profile (optional)
export DEPLOYMENT_ACCOUNT="123456789012"      # Your AWS account ID
export DEPLOYMENT_REGION="us-east-1"          # Target AWS region
export DEPLOYMENT_STAGE="dev"                 # dev, staging, or prod
export STACK_DISAMBIGUATOR="my-unique-id"     # Unique identifier for stacks
```

**2. Install Dependencies**

```bash
npm install
```

**3. Build the Project**

```bash
npm run build
```

**4. Bootstrap CDK (First Time Only)**

```bash
npx cdk bootstrap aws://${DEPLOYMENT_ACCOUNT}/${DEPLOYMENT_REGION}
```

**5. Deploy All Stacks**

```bash
npx cdk deploy --all
```

**6. Configure IAM Permissions for Running Patterns**

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

This policy grants permission to assume the execution role (`NovaAct-HITL-ExecutionRole-*`) which is required to run the human intervention patterns. See `lib/executors/websocketExecutorStack.ts` (line 410) for the policy definition.

## Deployment Script

The `setup-and-deploy.sh` script provides a user-friendly interface for deploying this CDK application. It handles:

- ✅ First-time AWS user setup with guided wizard
- ✅ AWS credential configuration with named profiles
- ✅ Dependency installation and project building
- ✅ CDK bootstrapping and deployment
- ✅ Stack output viewing
- ✅ Notification configuration (Slack, Email)

**Common commands:**
```bash
# Interactive mode (menu-driven)
./setup-and-deploy.sh -i

# Deploy with custom configuration
./setup-and-deploy.sh -s prod -d prod-alpha -r us-west-2 deploy

# Show deployed stack outputs
./setup-and-deploy.sh outputs

# Destroy all stacks
./setup-and-deploy.sh destroy
```

**For detailed documentation, see [CLI-GUIDE.md](./CLI-GUIDE.md)**

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AWS_PROFILE` | AWS CLI profile name | `default` | No |
| `DEPLOYMENT_ACCOUNT` | AWS Account ID | Detected from credentials | Yes |
| `DEPLOYMENT_REGION` | AWS Region | `us-east-1` | Yes |
| `DEPLOYMENT_STAGE` | Deployment stage | `dev` | Yes |
| `STACK_DISAMBIGUATOR` | Unique stack identifier | Same as `DEPLOYMENT_STAGE` | No |

**Configuration Priority (highest to lowest):**
1. Command-line options (`-s`, `-d`, `-r`, `-a`)
2. Environment variables
3. Auto-detected values (from AWS credentials)
4. Default values

## Notifications Setup

The service supports **Slack** and **Email (AWS SES)** notifications for workflow events.

### Configuring Notification Channels in CDK

Enable notifications when deploying stacks in `bin/app.ts`:

```typescript
import { NotificationChannel } from '../lib/models/types';

const approvalStack = new ApprovalStepFunctionStack(app, 'Approval', {
  // ... other props
  notificationChannels: [NotificationChannel.SLACK, NotificationChannel.EMAIL],
  // slackSecretsName is automatically set to the secret created by Storage Stack
});

const uiTakeoverStack = new UITakeoverStepFunctionStack(app, 'UITakeover', {
  // ... other props
  notificationChannels: [NotificationChannel.SLACK, NotificationChannel.EMAIL],
  // slackSecretsName is automatically set to the secret created by Storage Stack
});
```

### Slack Setup Summary

#### Quick Setup (Using App Manifests - Recommended)

The fastest way to set up Slack apps is using the provided manifest files:

1. **Create Slack App** at [api.slack.com/apps](https://api.slack.com/apps) → "Create New App" → **"From an app manifest"**
2. **Select your workspace**
3. **Paste the manifest** from either:
   - `slack-app-manifests/Approval.json` (for Approval pattern)
   - `slack-app-manifests/UITakeover.json` (for UI Takeover pattern)
4. **Review and create** the app
5. **Install to Workspace** and copy the Bot User OAuth Token (starts with `xoxb-`)
6. **Deploy the CDK stacks first** (the Storage Stack automatically creates the Slack secret with name: `nova-act-slack-secrets-${disambiguator}`)
7. **Update the secret with your bot tokens**:

```bash
# Get the actual secret name from your deployment outputs
./setup-and-deploy.sh outputs | grep -i slack

# Or use the pattern: nova-act-slack-secrets-{your-disambiguator}
# For example, if your disambiguator is "dev":
aws secretsmanager update-secret \
  --secret-id "nova-act-slack-secrets-dev" \
  --secret-string '{"UITakeover":"xoxb-token","Approval":"xoxb-token"}' \
  --region us-east-1
```

The manifests automatically configure:
- OAuth scopes: `chat:write`, `chat:write.customize`, `links:write`, and `channels:read`
- Bot user display name
- Basic interactivity settings

**Note:** The secret is created automatically by the Storage Stack when SLACK notification channel is enabled.

#### Manual Setup

Alternatively, create a Slack app manually:

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps) → "From scratch"
2. Add OAuth scopes under OAuth & Permissions → Bot Token Scopes: `chat:write`, `chat:write.customize`, `links:write`, and `channels:read`
3. Install to workspace and copy Bot User OAuth Token
4. Store token in AWS Secrets Manager (same command as above)

#### Usage

After setup, get your Channel ID (right-click channel → View channel details) and include Slack recipients when invoking Step Functions. See the [parent README](../README.md#notifications-setup) for complete usage examples.

### AWS SES Setup Summary

1. Verify sender email address:

```bash
aws ses verify-email-identity \
  --email-address noreply@yourdomain.com \
  --region us-east-1
```

2. (Optional) Request production access in AWS SES Console to send to any email
3. (Optional) Verify your domain for DKIM signing

### Implementation Details

The notification system is implemented in `lambda-packages/handlers/amzn_nova_act_human_intervention/notifications/`:

- `notification_factory.py` - Orchestrates notifications across channels
- `slack_notifier.py` - Slack Bot SDK integration
- `email_notifier.py` - AWS SES integration with HTML templates
- `base.py` - Notification data models

Lambda IAM roles automatically receive:
- SES sending permissions (when Email channel enabled)
- Secrets Manager read permissions (when Slack channel enabled)

See the [parent README](../README.md#notifications-setup) for complete setup instructions and troubleshooting.

## Stack Architecture

The deployment creates 4 stacks with the following dependency structure:

```
StorageStack
    ↓
    ├── ApprovalStepFunctionStack
    └── UITakeoverStepFunctionStack
            ↓
    WebsocketExecutorStack
```

### Stack Naming Convention

Stacks are named using the pattern: `NovaActHITL-{StackType}-{Disambiguator}`

**Examples:**
- `NovaActHITL-Storage-dev`
- `NovaActHITL-Approval-dev`
- `NovaActHITL-UITakeover-dev`
- `NovaActHITL-WebSocket-dev`

## AWS Credentials Setup

### Option 1: Using the Setup Wizard (Recommended for New Users)

```bash
./setup-and-deploy.sh first-time-setup
```

This guided wizard will help you:
- Create an AWS account (if needed)
- Create an IAM user for deployments
- Generate access keys
- Configure credentials using a named profile (preserves existing credentials)

### Option 2: Configure Existing Credentials

If you already have AWS access keys:

```bash
./setup-and-deploy.sh configure
```

This will:
- Create a named AWS profile (default: `hitl-deployer`)
- Not overwrite your existing default AWS credentials
- Automatically set `AWS_PROFILE` for the current session

### Option 3: Manual Setup

If you prefer manual configuration:

```bash
# Create a named profile
aws configure --profile hitl-deployer

# Then use it
export AWS_PROFILE=hitl-deployer
```

**Required IAM Permissions:**
- `AdministratorAccess` (for development), or
- Custom policy with CDK deployment permissions

**For detailed instructions, see [CLI-GUIDE.md](./CLI-GUIDE.md) → First-Time AWS User Setup**

## Common Commands

**Note:** Run these commands from the `cdk/` directory.

### Using the Deployment Script

```bash
# List available stacks
./setup-and-deploy.sh list

# Preview changes
./setup-and-deploy.sh diff

# Synthesize CloudFormation templates
./setup-and-deploy.sh synth

# Deploy specific stack
./setup-and-deploy.sh deploy-stack NovaActHITL-Storage-dev

# Deploy with custom configuration
./setup-and-deploy.sh -s staging -r us-west-2 deploy

# Show deployed stack outputs
./setup-and-deploy.sh outputs

# Show client environment variables (for SDK usage)
./setup-and-deploy.sh client-env

# Check deployment readiness
./setup-and-deploy.sh verify

# Destroy all stacks
./setup-and-deploy.sh destroy
```

### Using CDK Commands Directly

```bash
# List all stacks
npx cdk list

# Preview changes (diff)
npx cdk diff

# Synthesize CloudFormation templates
npx cdk synth

# Deploy specific stack
npx cdk deploy NovaActHITL-Storage-dev

# Destroy all stacks
npx cdk destroy --all
```

## Troubleshooting

### Error: "No AWS credentials configured"

**Solution:** Use the setup wizard or configure credentials:
```bash
# Option 1: Setup wizard (recommended for new users)
./setup-and-deploy.sh first-time-setup

# Option 2: Configure existing credentials
./setup-and-deploy.sh configure

# Option 3: Manual AWS CLI
aws configure --profile hitl-deployer
export AWS_PROFILE=hitl-deployer
```

### Error: "This stack uses assets, so the toolkit stack must be deployed"

**Solution:** Bootstrap CDK first:
```bash
./setup-and-deploy.sh bootstrap
# OR
npx cdk bootstrap
```

### Error: "Stack already exists"

**Solution:** Use a different disambiguator:
```bash
# Using command-line option
./setup-and-deploy.sh -d my-custom-name deploy

# Using environment variable
export STACK_DISAMBIGUATOR="my-custom-name"
./setup-and-deploy.sh deploy
```

### Build Errors

**Solution:** Clean and rebuild:
```bash
# Using deployment script
./setup-and-deploy.sh prepare

# OR manually
npm run clean
npm install
npm run build
```

### Need More Help?

**Check deployment readiness:**
```bash
./setup-and-deploy.sh verify
```

**View detailed help:**
```bash
./setup-and-deploy.sh help
```

**Comprehensive troubleshooting guide:** See [CLI-GUIDE.md](./CLI-GUIDE.md) → Troubleshooting section

## Project Structure

This CDK application structure (within the `cdk/` directory):

```
cdk/
├── bin/
│   └── app.ts                    # CDK app entry point (deployment)
├── lib/
│   ├── index.ts                  # Library exports (for npm package)
│   ├── storage/                  # Storage stack (DynamoDB, S3, CloudFront)
│   ├── executors/                # WebSocket executor stack
│   ├── stepFunctions/            # Step function stacks
│   ├── models/                   # Types and constants
│   └── utils/                    # Utility functions
├── lambda-packages/              # Pre-built Lambda deployment packages
│   └── handlers/                 # Lambda handler code and dependencies
├── scripts/
│   └── rebuild-lambda.sh         # Script to rebuild Lambda packages from SDK
├── package.json
├── tsconfig.json
└── cdk.json
```

The Lambda packages are built from the Python SDK source in `../sdk/`.

## Stack Outputs

After deployment, each stack will output important resource identifiers:

### Storage Stack
- DynamoDB table names (connections, executions)
- S3 bucket names
- CloudFront distribution URL

### Step Function Stacks
- State machine ARNs
- Screenshot bucket names

### WebSocket Stack
- WebSocket API endpoint URL
- API Gateway ID
- IAM execution role ARN

### View Stack Outputs

**Using the deployment script:**
```bash
# Show all stack outputs
./setup-and-deploy.sh outputs

# Show client environment variables (for SDK usage)
./setup-and-deploy.sh client-env
```

**Using AWS CLI:**
```bash
aws cloudformation describe-stacks \
  --region ${DEPLOYMENT_REGION} \
  --stack-name NovaActHITL-Storage-${STACK_DISAMBIGUATOR}
```

## Cleanup

To remove all deployed resources:

**Using the deployment script:**
```bash
./setup-and-deploy.sh destroy
```

**Using CDK directly:**
```bash
npx cdk destroy --all
```

⚠️ **Warning:** This will permanently delete all resources, including DynamoDB tables and S3 buckets (if empty).

## Python SDK

The Python SDK packages are located in the `../sdk/` directory:

- **Service** (`../sdk/service/`): Lambda handler code
- **Client** (`../sdk/client/`): Python client library for connecting to the service
- **Common** (`../sdk/common/`): Shared utilities

For information about using the Python client library or modifying the SDK, see:
- [SDK Overview](../sdk/README.md)
- [Client Documentation](../sdk/client/README.md)
- [Service Documentation](../sdk/service/README.md)

### Rebuilding Lambda Packages

If you modify the SDK source code, rebuild the Lambda deployment packages:

```bash
cd scripts
./rebuild-lambda.sh
```

This will copy the latest code from `../sdk/service/` and `../sdk/common/`, install dependencies, and create deployment packages in `lambda-packages/`.

## Documentation

- **[CLI-GUIDE.md](./CLI-GUIDE.md)** - Comprehensive deployment script guide
  - First-time AWS user setup with detailed instructions
  - All deployment script commands and options
  - Common workflows and examples
  - Troubleshooting guide

- **[Parent README](../README.md)** - Main project overview

- **Python SDK Documentation**
  - [SDK Overview](../sdk/README.md)
  - [Client Package](../sdk/client/README.md) - Python client library usage
  - [Service Package](../sdk/service/README.md) - Lambda handler implementation
  - [Common Package](../sdk/common/README.md) - Shared utilities

## Support

For issues or questions:

**1. Check the documentation:**
```bash
# View script help
./setup-and-deploy.sh help

# Check deployment readiness
./setup-and-deploy.sh verify
```

**2. Review the guides:**
- [Troubleshooting](#troubleshooting) section in this README
- [CLI-GUIDE.md](./CLI-GUIDE.md) → Troubleshooting section
- [Parent README](../README.md) for project overview

**3. Check AWS resources:**
- Review CloudWatch Logs for Lambda functions
- Check CloudFormation stack events in AWS Console
- View stack outputs: `./setup-and-deploy.sh outputs`

## Additional Resources

- [Parent Project README](../README.md)
- [Python SDK Documentation](../sdk/README.md)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [AWS Step Functions](https://docs.aws.amazon.com/step-functions/)
- [AWS API Gateway WebSocket APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api.html)
- [AWS CLI Configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
