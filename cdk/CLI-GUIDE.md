# CLI Deployment Guide

Complete guide for using the `setup-and-deploy.sh` script to deploy Nova Act Human Intervention CDK stacks.

## Table of Contents

- [First-Time AWS User Setup](#first-time-aws-user-setup)
- [Quick Start](#quick-start)
- [Script Modes](#script-modes)
- [Configuration](#configuration)
- [Common Workflows](#common-workflows)
- [Command Reference](#command-reference)
- [Automated Deployment](#automated-deployment)
- [Troubleshooting](#troubleshooting)

---

## First-Time AWS User Setup

**New to AWS?** This section guides you through creating your AWS account and setting up credentials for deployment.

### Step 1: Create an AWS Account

If you don't have an AWS account yet:

1. Go to [https://aws.amazon.com/](https://aws.amazon.com/)
2. Click **Create an AWS Account**
3. Follow the registration process:
   - Enter your email address and password
   - Provide contact information
   - Enter payment information (credit card required, but you can use free tier)
   - Verify your identity (phone verification)
   - Select a support plan (free "Basic Support" is fine)
4. Wait for account activation (can take a few minutes)

### Step 2: Sign In to AWS Console

1. Go to [https://console.aws.amazon.com/](https://console.aws.amazon.com/)
2. Sign in with your root account email and password
3. You should see the AWS Management Console

### Step 3: Create an IAM User for Deployment

**Important:** Never use your root account credentials for deployments. Create an IAM user instead.

#### Option A: Using AWS Console (Recommended for Beginners)

**Create IAM User:**

1. In AWS Console, search for **IAM** and click on it
2. Click **Users** in the left sidebar
3. Click **Create user** button
4. **User details:**
   - User name: `cdk-deployer` (or your preferred name)
   - Click **Next**

5. **Set permissions:**
   - Choose: **Attach policies directly**
   - Search for and select: `AdministratorAccess`
   - ⚠️ **Note:** This gives full access. For production, use the custom policy (see Option B)
   - Click **Next**

6. **Review and create:**
   - Review settings
   - Click **Create user**

**Create Access Keys:**

1. Click on the newly created user (`cdk-deployer`)
2. Go to the **Security credentials** tab
3. Scroll down to **Access keys** section
4. Click **Create access key**
5. Select use case: **Command Line Interface (CLI)**
6. Check the confirmation checkbox: "I understand..."
7. Click **Next**
8. (Optional) Add a description tag
9. Click **Create access key**

10. **⚠️ IMPORTANT - Save your credentials:**
    ```
    Access Key ID: AKIAIOSFODNN7EXAMPLE
    Secret Access Key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    ```

11. Click **Download .csv file** to save these credentials
12. Click **Done**

**⚠️ Security Warning:** You cannot view the secret access key again. Save it securely!

#### Option B: Using the Deployment Script (Automated)

The script can create an IAM user for you if you already have admin credentials:

```bash
./setup-and-deploy.sh create-user
# OR
./setup-and-deploy.sh -i
# Select option 3: Create new IAM user and access keys
```

This will:
- Create a new IAM user named `hitl-cdk-deployer`
- Create and attach appropriate IAM policies
- Generate access keys
- Save credentials to a file

#### Option C: Using Custom IAM Policy (Production - Least Privilege)

For production environments, use the minimum required permissions:

1. In IAM Console, go to **Policies**
2. Click **Create policy**
3. Switch to **JSON** tab
4. Copy the contents of `cdk-deployer-policy.json` from this repository
5. Paste into the JSON editor
6. Click **Next**
7. Policy name: `NovaActHITL-CDK-Deployer-Policy`
8. Click **Create policy**

Then create a user and attach this policy instead of AdministratorAccess.

### Step 4: Configure AWS CLI Credentials

Once you have your Access Key ID and Secret Access Key:

#### Option A: Using the Deployment Script (Easiest - Recommended)

```bash
./setup-and-deploy.sh configure
# OR
./setup-and-deploy.sh -i
# Select option 3: Configure existing credentials
```

**What happens:**
- You'll be prompted for a profile name (default: `hitl-deployer`)
- Enter your AWS Access Key ID
- Enter your AWS Secret Access Key
- Credentials are stored in a named profile (won't overwrite your default AWS credentials)
- The script automatically sets `AWS_PROFILE` for the current session

**Interactive prompts:**
```
Enter AWS profile name [hitl-deployer]:
Enter AWS Access Key ID: AKIAIOSFODNN7EXAMPLE
Enter AWS Secret Access Key: ********

✅ Credentials configured for profile: hitl-deployer

To use this profile in future sessions:
  Option 1: export AWS_PROFILE=hitl-deployer
  Option 2: AWS_PROFILE=hitl-deployer ./setup-and-deploy.sh deploy
```

**Benefits of named profiles:**
- Keeps your existing AWS credentials intact
- Allows multiple AWS accounts/credentials on the same machine
- More professional and safer practice
- Easy to switch between different environments

#### Option B: Using AWS CLI Directly with Profile

```bash
aws configure --profile hitl-deployer
```

Enter when prompted:
```
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-east-1
Default output format [None]: json
```

Then use the profile:
```bash
export AWS_PROFILE=hitl-deployer
./setup-and-deploy.sh deploy
```

#### Option C: Manual Configuration with Profile

Create or edit `~/.aws/credentials` file:

```ini
[hitl-deployer]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

Create or edit `~/.aws/config` file:

```ini
[profile hitl-deployer]
region = us-east-1
output = json
```

Then use the profile:
```bash
export AWS_PROFILE=hitl-deployer
```

#### Option D: Using Default Profile (Not Recommended)

If you prefer to use the default profile (will overwrite existing credentials):

```bash
aws configure
```

This approach is **not recommended** because:
- Overwrites your existing default AWS credentials
- Can't easily switch between multiple AWS accounts
- Less secure in shared environments

### Step 5: Verify Your Credentials

```bash
./setup-and-deploy.sh check-credentials
# OR
aws sts get-caller-identity
```

**Expected output:**
```
✅ AWS credentials are configured
   Account: 123456789012
   Identity: arn:aws:iam::123456789012:user/cdk-deployer
   Region: us-east-1
```

### Step 6: Understand AWS Costs

**Free Tier Resources:**
- DynamoDB: 25 GB storage, 25 read/write capacity units
- Lambda: 1 million free requests/month, 400,000 GB-seconds compute
- S3: 5 GB storage, 20,000 GET requests, 2,000 PUT requests
- CloudWatch: 10 custom metrics, 10 alarms

**Resources That May Cost Money:**
- CloudFront distributions (outside free tier)
- API Gateway WebSocket connections (outside free tier)
- SES email sending (outside free tier)

**Cost Estimation:**
For development/testing with minimal traffic: **$1-5/month**
For production with moderate traffic: **$10-50/month**

**Cost Monitoring:**
1. Set up billing alerts in AWS Console
2. Go to **Billing and Cost Management** → **Budgets**
3. Create a budget with alerts (e.g., alert if costs exceed $10/month)

### Step 7: Your First Deployment

Now you're ready to deploy! Follow the [Quick Start](#quick-start) section.

**Complete first deployment:**
```bash
# Check credentials (you already did this)
./setup-and-deploy.sh check-credentials

# Use interactive mode for guided deployment
./setup-and-deploy.sh -i
# Select option 17: Full deployment workflow

# OR use command mode
./setup-and-deploy.sh prepare
./setup-and-deploy.sh bootstrap  # First time only
./setup-and-deploy.sh deploy
```

### Common First-Time User Issues

#### "Access Denied" Errors

**Problem:** Your IAM user doesn't have sufficient permissions.

**Solution:**
- Verify the user has `AdministratorAccess` or the custom CDK deployer policy
- Check in IAM Console → Users → [your user] → Permissions tab

#### "Region Not Enabled" Error

**Problem:** Some AWS regions are disabled by default.

**Solution:**
- Use a standard region like `us-east-1`, `us-west-2`, or `eu-west-1`
- Or enable the region in AWS Console → Account settings

#### "Account Not Verified" Error

**Problem:** AWS account verification is still pending.

**Solution:**
- Check your email for verification messages from AWS
- Complete phone verification if prompted
- Wait a few minutes for account activation

#### Can't Find IAM in Console

**Problem:** You're not signed in as root user or don't have permissions.

**Solution:**
- Sign out and sign in as root user (the account creator)
- IAM is at: [https://console.aws.amazon.com/iam/](https://console.aws.amazon.com/iam/)

#### "Credentials could not be loaded" Error

**Problem:** AWS CLI can't find your credentials.

**Solution:**
```bash
# Reconfigure credentials
./setup-and-deploy.sh configure

# Or check if credentials file exists
ls ~/.aws/credentials
cat ~/.aws/credentials  # Should show your access keys
```

### Security Best Practices for Beginners

1. **Never commit credentials to git**
   - Don't add credentials to your code
   - Don't share access keys in chat/email
   - Use AWS Secrets Manager for application secrets

2. **Rotate access keys regularly**
   - Create new keys every 90 days
   - Delete old keys after rotation
   - Use the script: `./setup-and-deploy.sh create-user`

3. **Enable MFA (Multi-Factor Authentication)**
   - Go to IAM → Users → [your user] → Security credentials
   - Assign MFA device (use Google Authenticator or similar app)
   - This prevents unauthorized access even if credentials are leaked

4. **Use separate environments**
   - Dev: `./setup-and-deploy.sh -s dev deploy`
   - Staging: `./setup-and-deploy.sh -s staging deploy`
   - Prod: `./setup-and-deploy.sh -s prod deploy`

5. **Monitor your AWS billing**
   - Set up billing alerts
   - Review monthly bills
   - Delete unused resources

---

## Quick Start

### First Time Setup

**🎓 New to AWS?** Use the guided setup wizard:

```bash
./setup-and-deploy.sh first-time-setup
```

This interactive wizard will:
- Guide you through creating AWS credentials
- Configure them for you
- Optionally start the deployment

**Already have AWS credentials?** Follow these steps:

```bash
# 1. Check your AWS credentials
./setup-and-deploy.sh

# 2. If credentials are configured, use interactive mode
./setup-and-deploy.sh -i
# Select option 18 for full deployment workflow

# OR use command mode for automated deployment
./setup-and-deploy.sh prepare
./setup-and-deploy.sh bootstrap
./setup-and-deploy.sh deploy
```

### Quick Deployment (Already Configured)

```bash
# One-command deployment
./setup-and-deploy.sh quick-deploy
```

---

## Script Modes

The script supports three distinct modes:

### 1. Default Mode (Credential Check)

Running the script without arguments performs a quick credential check.

```bash
./setup-and-deploy.sh
```

**Output:**
```
Checking current AWS credentials...
✅ AWS credentials are configured
   Account: 123456789012
   Identity: arn:aws:iam::123456789012:user/deployer
   Region: us-east-1
```

**Use when:**
- Verifying your AWS setup
- Checking which account you're deploying to
- Quick sanity check before deployment

### 2. Interactive Mode (Menu)

Shows a full interactive menu with 21 options.

```bash
./setup-and-deploy.sh -i
# OR
./setup-and-deploy.sh --interactive
```

**Use when:**
- Learning the available commands
- First-time setup
- Performing multiple operations
- Exploring deployment options

### 3. Command Mode (Automation)

Execute specific commands directly.

```bash
./setup-and-deploy.sh <command>
```

**Use when:**
- Automating deployments
- CI/CD pipelines
- Scripting workflows
- You know exactly what you want to do

---

## Configuration

The script supports multiple ways to configure deployment settings, with command-line options taking highest priority.

### Configuration Priority (Highest to Lowest)

1. **Command-line options** (override everything)
2. **Environment variables**
3. **Auto-detected values** (from AWS credentials)
4. **Default values**

### Configuration Variables

| Variable | Description | Auto-Detected | Default |
|----------|-------------|---------------|---------|
| `AWS_PROFILE` | AWS CLI profile name | ❌ No | default (uses ~/.aws/credentials default profile) |
| `DEPLOYMENT_ACCOUNT` | AWS Account ID | ✅ Yes | Detected from credentials |
| `DEPLOYMENT_REGION` | AWS Region | ✅ Yes | us-east-1 |
| `DEPLOYMENT_STAGE` | Deployment stage | ❌ No | test |
| `STACK_DISAMBIGUATOR` | Stack naming suffix | ❌ No | Same as DEPLOYMENT_STAGE |

### Command-Line Options

You can override any configuration using command-line options:

| Option | Long Form | Description |
|--------|-----------|-------------|
| `-s STAGE` | `--stage STAGE` | Set deployment stage |
| `-d VALUE` | `--disambiguator VALUE` | Set stack disambiguator |
| `-r REGION` | `--region REGION` | Set AWS region |
| `-a ACCOUNT` | `--account ACCOUNT` | Set AWS account ID |

**Examples:**
```bash
# Deploy to prod in us-west-2 using a named profile
export AWS_PROFILE=hitl-deployer
./setup-and-deploy.sh -s prod -r us-west-2 deploy

# Deploy with custom disambiguator and profile
AWS_PROFILE=hitl-deployer ./setup-and-deploy.sh -s prod -d prod-alpha -r us-west-2 quick-deploy

# Command-line options override environment variables
export DEPLOYMENT_STAGE=dev
./setup-and-deploy.sh -s prod deploy  # Uses prod, not dev

# Mix and match (options override env vars)
export DEPLOYMENT_REGION=us-east-1
export AWS_PROFILE=hitl-deployer
./setup-and-deploy.sh -r us-west-2 -s staging deploy

# Use different profiles for different environments
AWS_PROFILE=dev-profile ./setup-and-deploy.sh -s dev deploy
AWS_PROFILE=prod-profile ./setup-and-deploy.sh -s prod deploy
```

### Setting Variables with Environment Variables

**Option 1: Export before running (with AWS profile)**
```bash
export AWS_PROFILE=hitl-deployer
export DEPLOYMENT_STAGE=prod
export STACK_DISAMBIGUATOR=prod-v2
export DEPLOYMENT_REGION=us-west-2
./setup-and-deploy.sh deploy
```

**Option 2: Inline with command**
```bash
AWS_PROFILE=hitl-deployer DEPLOYMENT_STAGE=staging ./setup-and-deploy.sh quick-deploy
```

**Option 3: Interactive configuration**
```bash
./setup-and-deploy.sh -i
# Select option 7: Configure deployment environment variables
```

**Option 4: Command-line options (Recommended for CI/CD)**
```bash
# Cleanest syntax, no need to export
AWS_PROFILE=hitl-deployer ./setup-and-deploy.sh -s staging -r us-west-2 deploy
```

**Option 5: Add to your shell profile (persistent)**
```bash
# Add to ~/.bashrc or ~/.zshrc
echo 'export AWS_PROFILE=hitl-deployer' >> ~/.bashrc
source ~/.bashrc

# Now all AWS commands use this profile by default
./setup-and-deploy.sh deploy
```

### Auto-Detection Behavior

```bash
# No variables set - auto-detects account and region
./setup-and-deploy.sh
# Output: Account: 123456789012, Region: us-east-1

# Override detection
export DEPLOYMENT_ACCOUNT=999999999999
./setup-and-deploy.sh
# Output: Account: 999999999999, Region: us-east-1 (still detected)
```

---

## Common Workflows

### Workflow 1: First-Time Deployment

```bash
#!/bin/bash
# Complete first-time setup and deployment

# Step 1: Configure environment (optional - uses auto-detection otherwise)
export DEPLOYMENT_STAGE=dev
export STACK_DISAMBIGUATOR=dev-team-alpha

# Step 2: Check credentials
./setup-and-deploy.sh check-credentials

# Step 3: Prepare stacks (install + build + synth)
./setup-and-deploy.sh prepare

# Step 4: Bootstrap CDK (first time only)
./setup-and-deploy.sh bootstrap

# Step 5: Review what will be deployed
./setup-and-deploy.sh diff

# Step 6: Deploy all stacks
./setup-and-deploy.sh deploy
# Note: This will automatically prompt you to configure Slack tokens and email identities

# Step 7: View deployed resources
./setup-and-deploy.sh outputs

# Step 8 (optional): Configure notifications if skipped during deployment
./setup-and-deploy.sh configure-slack-secrets  # Slack tokens
./setup-and-deploy.sh configure-email    # SES email identities

# Step 9 (optional): Verify email identities are ready
./setup-and-deploy.sh check-email-status
```

### Workflow 2: Update Existing Deployment

```bash
#!/bin/bash
# Update code and redeploy

# Step 1: Build the latest code
./setup-and-deploy.sh build

# Step 2: Check what changed
./setup-and-deploy.sh diff

# Step 3: Deploy changes
./setup-and-deploy.sh deploy
```

### Workflow 3: Quick Update (No Review)

```bash
# Build and deploy in one command
./setup-and-deploy.sh quick-deploy
```

### Workflow 4: Deploy to Multiple Environments

**Using command-line options (recommended):**
```bash
#!/bin/bash
# Deploy to dev, staging, and prod using command-line options

environments=("dev" "staging" "prod")
regions=("us-east-1" "us-east-1" "us-west-2")

for i in "${!environments[@]}"; do
  env="${environments[$i]}"
  region="${regions[$i]}"

  echo "Deploying to $env in $region..."

  ./setup-and-deploy.sh -s "$env" -r "$region" prepare
  ./setup-and-deploy.sh -s "$env" -r "$region" deploy

  echo "$env deployment complete!"
done
```

**Using environment variables:**
```bash
#!/bin/bash
# Deploy to dev, staging, and prod using environment variables

environments=("dev" "staging" "prod")

for env in "${environments[@]}"; do
  echo "Deploying to $env..."

  export DEPLOYMENT_STAGE=$env
  export STACK_DISAMBIGUATOR=$env

  ./setup-and-deploy.sh prepare
  ./setup-and-deploy.sh deploy

  echo "$env deployment complete!"
done
```

### Workflow 5: Deploy Individual Stack

```bash
# Syntax: deploy-stack <stack-name>

# Deploy only the storage stack
./setup-and-deploy.sh deploy-stack NovaActHITL-Storage-test

# Deploy only the approval workflow stack
./setup-and-deploy.sh deploy-stack NovaActHITL-Approval-test
```

### Workflow 6: Configure Notifications (Slack and Email)

```bash
#!/bin/bash
# Complete notification setup

# Option 1: During deployment (automatic prompts)
./setup-and-deploy.sh deploy
# Will prompt for both Slack and email configuration

# Option 2: Standalone configuration
./setup-and-deploy.sh configure-slack-secrets  # Configure Slack tokens
./setup-and-deploy.sh configure-email    # Configure email identities

# Option 3: Verify email verification status
./setup-and-deploy.sh check-email-status
```

**Slack token rotation (security best practice):**
- Rotate every 90 days
- When a team member with access leaves
- After suspected credential compromise
- When switching Slack workspaces

**Email identity management:**
- Verify both FROM and TO addresses in SES
- Check verification status before testing
- Re-verify if changing email addresses
- Request production access to remove TO verification requirement

### Workflow 7: Troubleshoot Email Delivery

```bash
#!/bin/bash
# Debug email notification issues

# Step 1: Check email verification status
./setup-and-deploy.sh check-email-status

# Step 2: If pending, wait for verification emails and click links

# Step 3: Re-check status after verifying
./setup-and-deploy.sh check-email-status

# Step 4: If verified but emails not arriving, check SES sandbox status
# You may need to request production access in AWS Console:
# SES → Account dashboard → Request production access
```

**Common email issues:**
- **Emails not arriving**: Check SES sandbox status, verify both emails
- **Verification pending**: Check spam folder for AWS verification emails
- **Verification expired**: Run `configure-email` again to resend verification
- **Wrong email addresses**: Run `configure-email` again with correct addresses

### Workflow 8: Clean Deployment (Destroy and Recreate)

```bash
#!/bin/bash
# Completely remove and redeploy everything

echo "⚠️  This will DELETE all existing resources!"
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" = "yes" ]; then
  # Destroy all stacks
  ./setup-and-deploy.sh destroy

  # Wait a moment for cleanup
  sleep 10

  # Redeploy everything
  ./setup-and-deploy.sh prepare
  ./setup-and-deploy.sh deploy

  # Configure notifications for new deployment
  ./setup-and-deploy.sh configure-slack-secrets  # Slack tokens
  ./setup-and-deploy.sh configure-email    # Email identities
  ./setup-and-deploy.sh check-email-status # Verify emails
fi
```

---

## Command Reference

### Setup Commands

#### `first-time-setup` (aliases: `first-time`, `new-user`, `wizard`)
🎓 **Guided setup wizard for first-time AWS users.**

```bash
./setup-and-deploy.sh first-time-setup
```

**What it does:**
- Checks if you already have AWS credentials configured
- If not, provides step-by-step instructions for:
  - Creating an AWS account
  - Creating an IAM user
  - Generating access keys
  - Configuring credentials locally
- Verifies your credentials work correctly
- Optionally launches the full deployment workflow

**When to use:**
- You're new to AWS and need guidance
- You want a guided walkthrough of the setup process
- You're unsure how to get started

**Interactive prompts:**
```
🎓 First-Time AWS User Setup Wizard
This wizard will help you set up AWS credentials for deployment.

Have you completed steps 1-3 above and have your access keys ready? (y/n):
```

If you answer "no", it provides detailed step-by-step instructions.
If you answer "yes", it guides you through credential configuration.

**After successful setup:**
- Shows your configured AWS account and region
- Offers to run the full deployment workflow
- Provides next steps for deployment

#### `check-credentials` (alias: `check`)
Check current AWS credentials and configuration.

```bash
./setup-and-deploy.sh check-credentials
```

**Example output:**
```
✅ AWS credentials are configured
   Account: 123456789012
   Identity: arn:aws:iam::123456789012:user/deployer
   Region: us-east-1
```

#### `configure` (alias: `config`)
Configure AWS credentials interactively.

```bash
./setup-and-deploy.sh configure
# Prompts for Access Key ID and Secret Access Key
```

#### `show-env` (alias: `env`)
Display current environment configuration.

```bash
./setup-and-deploy.sh show-env
```

**Example output:**
```
Environment Variables:
  DEPLOYMENT_STAGE:       prod
  STACK_DISAMBIGUATOR:    prod-v2
  DEPLOYMENT_REGION:      us-west-2
  DEPLOYMENT_ACCOUNT:     123456789012

Stack Names:
  1. NovaActHITL-Storage-prod-v2
  2. NovaActHITL-Approval-prod-v2
  3. NovaActHITL-UITakeover-prod-v2
  4. NovaActHITL-WebSocket-prod-v2
```

#### `configure-env` (alias: `set-env`)
Configure deployment environment variables interactively.

```bash
./setup-and-deploy.sh configure-env
# Interactive prompts for stage, disambiguator, region
```

---

### Build & Deploy Commands

#### `prepare` (alias: `prep`)
**Combined**: Install dependencies, build project, and synthesize CDK templates.

```bash
./setup-and-deploy.sh prepare
```

Equivalent to:
```bash
npm install
npm run build
npx cdk synth
```

#### `install`
Install npm dependencies only.

```bash
./setup-and-deploy.sh install
```

#### `build`
Build the TypeScript project only.

```bash
./setup-and-deploy.sh build
```

#### `bootstrap`
Bootstrap CDK in your AWS account (first-time setup).

```bash
./setup-and-deploy.sh bootstrap
```

**When to run:**
- First deployment to an AWS account/region
- After upgrading CDK to a new version
- If you get "toolkit stack must be deployed" error

#### `list` (alias: `ls`)
List all available CDK stacks.

```bash
./setup-and-deploy.sh list
```

**Example output:**
```
NovaActHITL-Storage-test
NovaActHITL-Approval-test
NovaActHITL-UITakeover-test
NovaActHITL-WebSocket-test
```

#### `synth`
Synthesize CloudFormation templates (without deploying).

```bash
./setup-and-deploy.sh synth
```

**Use when:**
- Reviewing generated CloudFormation templates
- Debugging CDK code
- Validating stack configuration

#### `diff`
Show differences between deployed stacks and current code.

```bash
./setup-and-deploy.sh diff
```

**Example output:**
```
Stack NovaActHITL-Storage-test
Resources
[+] AWS::DynamoDB::Table ConnectionsTable-test ConnectionsTabletest
[~] AWS::S3::Bucket SpaBucket-test
 └─ [~] LifecycleConfiguration
     └─ [+] Rule DeleteTemporarySPAsAfter1Day
```

#### `deploy`
Deploy all CDK stacks.

```bash
./setup-and-deploy.sh deploy
```

**Deployment order:**
1. Storage stack
2. Approval stack
3. UITakeover stack
4. WebSocket stack

#### `deploy-stack <name>`
Deploy a specific stack by name.

```bash
./setup-and-deploy.sh deploy-stack NovaActHITL-Storage-test
```

#### `quick-deploy` (alias: `quick`)
**Fast deployment**: Build and deploy without prompts.

```bash
./setup-and-deploy.sh quick-deploy
```

Equivalent to:
```bash
npm run build
npx cdk deploy --all --require-approval never
```

#### `full` (alias: `full-deployment`)
**Complete workflow**: All steps from install to deploy.

```bash
./setup-and-deploy.sh full
```

**Steps performed:**
1. Check credentials
2. Configure environment (interactive)
3. Install dependencies
4. Check ts-node
5. Build project
6. Bootstrap CDK (optional)
7. List stacks
8. Synthesize templates
9. Show differences
10. Deploy all stacks

---

### Management Commands

#### `outputs` (alias: `output`)
Show deployed stack outputs (URLs, ARNs, etc.).

```bash
./setup-and-deploy.sh outputs
```

**Example output:**
```
--- NovaActHITL-Storage-test ---
OutputKey         OutputValue                                  Description
ConnectionsTable  HITL-Connections-test                       DynamoDB Connections Table
ExecutionsTable   HITL-Executions-test                        DynamoDB Executions Table
SpaBucketName     nova-act-hitl-spa-assets-123456789012-test  SPA Bucket Name
CloudFrontUrl     https://d111111abcdef8.cloudfront.net       CloudFront Distribution URL
```

#### `client-env` (aliases: `env-vars`)
Show environment variables needed for client scripts (e.g., usage examples).

```bash
./setup-and-deploy.sh client-env
```

**What it does:**
- Fetches WebSocket endpoint from WebSocket stack
- Fetches execution role ARN from WebSocket stack
- Fetches screenshot S3 bucket from Approval stack (optional)
- Displays values in both Python and shell export formats

**Example output:**
```
============================================
Environment Variables for Client Scripts
============================================

Copy these values to your client script or export them:

# Python script assignment:
HITL_EXECUTOR_ENDPOINT = "wss://abc123.execute-api.us-east-1.amazonaws.com/test"
HITL_IAM_ROLE_ARN = "arn:aws:iam::123456789012:role/NovaAct-HITL-ExecutionRole-test"
HITL_SCREENSHOT_S3_BUCKET = "hitl-approval-screenshots-test-123456789012"
AWS_REGION = "us-east-1"

# Shell export commands:
export HITL_EXECUTOR_ENDPOINT="wss://abc123.execute-api.us-east-1.amazonaws.com/test"
export HITL_IAM_ROLE_ARN="arn:aws:iam::123456789012:role/NovaAct-HITL-ExecutionRole-test"
export HITL_SCREENSHOT_S3_BUCKET="hitl-approval-screenshots-test-123456789012"
export AWS_REGION="us-east-1"
```

**When to use:**
- After deployment to get values for usage examples
- When setting up new client integrations
- For CI/CD pipelines that need these values

#### `configure-slack-secrets` (aliases: `slack-secrets`, `slack`)
Configure Slack bot tokens in AWS Secrets Manager.

```bash
./setup-and-deploy.sh configure-slack-secrets
```

**What it does:**
- Prompts for Slack bot token for Approval workflow (xoxb-...)
- Prompts for Slack bot token for UITakeover workflow (xoxb-...)
- Securely updates AWS Secrets Manager
- Validates secret exists before updating

**Interactive prompts:**
```
Enter Slack bot token for Approval workflow (starts with xoxb-): [hidden input]
Enter Slack bot token for UITakeover workflow (starts with xoxb-): [hidden input]
✅ Slack bot tokens configured successfully!
```

💡 **Tip:** You can enter the same token for both workflows if using a single Slack app.

**When to use:**
- After initial deployment
- When rotating Slack bot tokens
- When switching between Slack workspaces
- If you skipped configuration during deployment

**Note:** This is automatically prompted after successful deployment.

#### `configure-email` (alias: `email`)
Configure SES email identities for email notifications.

```bash
./setup-and-deploy.sh configure-email
```

**What it does:**
- Prompts for FROM email address (sender)
- Prompts for TO email address (recipient)
- Creates email identities in AWS SES
- Sends verification emails to both addresses
- Validates email format

**Interactive prompts:**
```
Enter FROM email address (sender): noreply@example.com
Enter TO email address (recipient): admin@example.com

✅ Email identities configured!

Next steps:
  1. Check the inboxes for both email addresses
  2. Click the verification links in the emails from AWS
  3. Wait a few minutes for verification to complete
```

**When to use:**
- After initial deployment
- When changing email addresses
- When setting up new environments
- If you skipped configuration during deployment

**Important:**
- Both email addresses must be verified to send emails
- In SES Sandbox mode, both sender and recipient must be verified
- Production access removes recipient verification requirement
- Verification links expire after 24 hours

**Note:** This is automatically prompted after successful deployment.

#### `check-email-status` (alias: `email-status`)
Check verification status of SES email identities.

```bash
./setup-and-deploy.sh check-email-status
```

**Example output:**
```
Region: us-east-1

Checking all email identities...

✅ noreply@example.com - Verified
⏳ admin@example.com - Pending (check inbox for verification email)
```

**Verification statuses:**
- ✅ **Verified** - Email is ready to use
- ⏳ **Pending** - Waiting for verification link click
- ❌ **Not verified** - Verification failed or expired

**When to use:**
- After configuring email identities
- When troubleshooting email delivery issues
- Before deploying to verify all emails are ready

#### `verify` (alias: `check-ready`)
Verify CDK deployment readiness.

```bash
./setup-and-deploy.sh verify
```

**Checks:**
- AWS credentials configured
- Node.js installed
- CDK app exists
- Dependencies installed
- Project built
- Lambda packages present

#### `destroy`
Destroy all deployed stacks.

```bash
./setup-and-deploy.sh destroy
```

**⚠️ Warning:**
- Deletes all AWS resources
- Data in DynamoDB and S3 will be lost
- Cannot be undone

---

## Troubleshooting

### Error: "No AWS credentials configured"

**Problem:** AWS credentials not set up.

**Solution:**
```bash
# Configure credentials
./setup-and-deploy.sh configure

# Or use AWS CLI
aws configure
```

---

### Error: "This stack uses assets, so the toolkit stack must be deployed"

**Problem:** CDK not bootstrapped in your AWS account/region.

**Solution:**
```bash
./setup-and-deploy.sh bootstrap
```

---

### Error: "Update canceled. Cannot update export... as it is in use"

**Problem:** CloudFormation export is referenced by other stacks.

**Solution:**
```bash
# Destroy all stacks and redeploy
./setup-and-deploy.sh destroy
./setup-and-deploy.sh deploy
```

---

### Error: "Circular dependency between stacks"

**Problem:** Stacks reference each other in a circular way.

**Solution:** This should be fixed in the current version. If you still see this:
```bash
# Clean rebuild
./setup-and-deploy.sh destroy
./setup-and-deploy.sh prepare
./setup-and-deploy.sh deploy
```

---

### Error: "ts-node not found"

**Problem:** TypeScript dependencies not installed.

**Solution:**
```bash
./setup-and-deploy.sh install
# OR
npm install
```

---

### Stack deployment hangs or times out

**Problem:** Large resources (CloudFront distributions) can take 10-30 minutes.

**Solution:**
- Wait patiently (CloudFront can take 20+ minutes)
- Check AWS CloudFormation console for progress
- Review CloudWatch logs for Lambda errors

---

### Changes not reflected after deployment

**Problem:** Forgot to build after code changes.

**Solution:**
```bash
./setup-and-deploy.sh build
./setup-and-deploy.sh deploy
# OR
./setup-and-deploy.sh quick-deploy
```

---

### "Stack already exists" error

**Problem:** Stack with the same disambiguator already deployed.

**Solution:**
```bash
# Option 1: Use a different disambiguator
export STACK_DISAMBIGUATOR=my-new-deployment
./setup-and-deploy.sh deploy

# Option 2: Update the existing stack
./setup-and-deploy.sh deploy
```

---

## Tips and Best Practices

### 1. Always Check Credentials First

```bash
./setup-and-deploy.sh check-credentials
```

Verify you're deploying to the correct account before running any deployment.

### 2. Use Disambiguators for Multiple Deployments

```bash
# Team A deployment
export STACK_DISAMBIGUATOR=team-a
./setup-and-deploy.sh deploy

# Team B deployment
export STACK_DISAMBIGUATOR=team-b
./setup-and-deploy.sh deploy
```

### 3. Review Changes Before Deploying

```bash
./setup-and-deploy.sh diff
# Review the output
./setup-and-deploy.sh deploy
```

### 4. Use Quick Deploy for Rapid Iteration

```bash
# Make code changes
vim lib/storage/storageStack.ts

# Quick rebuild and deploy
./setup-and-deploy.sh quick-deploy
```

### 5. Check Outputs After Deployment

```bash
./setup-and-deploy.sh outputs > deployment-outputs.txt
# Share with your team or save for reference
```

### 6. Test in Dev Before Prod

```bash
# Deploy to dev
export DEPLOYMENT_STAGE=dev
./setup-and-deploy.sh deploy

# Test thoroughly...

# Deploy to prod
export DEPLOYMENT_STAGE=prod
./setup-and-deploy.sh deploy
```

---

## Getting Help

### View available commands
```bash
./setup-and-deploy.sh help
./setup-and-deploy.sh --help
./setup-and-deploy.sh -h
```

### Use interactive mode to explore
```bash
./setup-and-deploy.sh -i
# Browse the menu to see all 21 options
```

### Check the documentation
- `README.md` - Project overview and quick start
- `PERMISSIONS-GUIDE.md` - IAM permissions reference
- `CLI-GUIDE.md` - This document

---

## Quick Reference

### Most Common Commands

```bash
# First time
./setup-and-deploy.sh check-credentials
./setup-and-deploy.sh prepare
./setup-and-deploy.sh bootstrap
./setup-and-deploy.sh deploy
./setup-and-deploy.sh configure-slack-secrets     # Configure Slack tokens
./setup-and-deploy.sh configure-email       # Configure SES emails
./setup-and-deploy.sh check-email-status    # Verify email setup

# Daily development
./setup-and-deploy.sh quick-deploy

# Check status
./setup-and-deploy.sh outputs
./setup-and-deploy.sh verify

# Clean up
./setup-and-deploy.sh destroy
```

### Command Aliases

| Full Command | Aliases |
|--------------|---------|
| `first-time-setup` | `first-time`, `new-user`, `wizard` |
| `check-credentials` | `check` |
| `configure` | `config` |
| `show-env` | `env` |
| `configure-env` | `set-env` |
| `prepare` | `prep` |
| `list` | `ls` |
| `quick-deploy` | `quick` |
| `full` | `full-deployment` |
| `outputs` | `output` |
| `client-env` | `env-vars` |
| `configure-slack-secrets` | `slack-secrets`, `slack` |
| `configure-email` | `email` |
| `check-email-status` | `email-status` |
| `verify` | `check-ready` |

---
