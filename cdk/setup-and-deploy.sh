#!/bin/bash

# AWS CDK Setup and Deployment Script for NovaAct Human Intervention
# This script helps you configure AWS credentials and deploy CDK stacks
# CDK Entry Point: bin/app.ts
# Default Target Region: us-east-1
#
# Environment Variables (can be set before running script):
#   AWS_PROFILE            - AWS CLI profile to use (e.g., hitl-deployer)
#   DEPLOYMENT_STAGE       - Deployment stage (default: dev)
#   STACK_DISAMBIGUATOR    - Unique stack identifier (default: same as DEPLOYMENT_STAGE)
#   DEPLOYMENT_REGION      - AWS region (default: us-east-2)
#   DEPLOYMENT_ACCOUNT     - AWS account ID (auto-detected from credentials)
#
# Command Line Options (override environment variables):
#   -s, --stage STAGE          - Deployment stage (overrides DEPLOYMENT_STAGE)
#   -d, --disambiguator VALUE  - Stack disambiguator (overrides STACK_DISAMBIGUATOR)
#   -r, --region REGION        - AWS region (overrides DEPLOYMENT_REGION)
#   -a, --account ACCOUNT      - AWS account ID (overrides DEPLOYMENT_ACCOUNT)
#
# Example with environment variables:
#   export AWS_PROFILE=hitl-deployer
#   export DEPLOYMENT_STAGE=prod
#   export STACK_DISAMBIGUATOR=prod-alpha
#   export DEPLOYMENT_REGION=us-west-2
#   ./setup-and-deploy.sh
#
# Example with command-line options:
#   AWS_PROFILE=hitl-deployer ./setup-and-deploy.sh -s prod -d prod-alpha -r us-west-2 deploy
#   ./setup-and-deploy.sh --stage dev --region us-east-1 quick-deploy

set -e

# Default values (can be overridden by environment variables)
DEFAULT_REGION="us-east-1"
IAM_USER_NAME="hitl-cdk-deployer"
CDK_APP_PATH="bin/app.ts"

# Parse command-line options (these override environment variables)
# Store non-option arguments (commands) for later processing
CMD_ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
    -s|--stage)
      export DEPLOYMENT_STAGE="$2"
      shift 2
      ;;
    -d|--disambiguator)
      export STACK_DISAMBIGUATOR="$2"
      shift 2
      ;;
    -r|--region)
      export DEPLOYMENT_REGION="$2"
      shift 2
      ;;
    -a|--account)
      export DEPLOYMENT_ACCOUNT="$2"
      shift 2
      ;;
    *)
      # Not one of our options, save it for later processing
      CMD_ARGS+=("$1")
      shift
      ;;
  esac
done

# Restore non-option arguments for command processing
set -- "${CMD_ARGS[@]}"

# Auto-detect AWS account from credentials if not already set
if [ -z "$DEPLOYMENT_ACCOUNT" ]; then
  if aws sts get-caller-identity &> /dev/null; then
    DETECTED_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    if [ -n "$DETECTED_ACCOUNT" ]; then
      export DEPLOYMENT_ACCOUNT="$DETECTED_ACCOUNT"
    fi
  fi
fi

# Auto-detect AWS region from credentials if not already set
if [ -z "$DEPLOYMENT_REGION" ] || [ "$DEPLOYMENT_REGION" = "$DEFAULT_REGION" ]; then
  DETECTED_REGION=$(aws configure get region 2>/dev/null)
  if [ -n "$DETECTED_REGION" ] && [ "$DETECTED_REGION" != "None" ]; then
    export DEPLOYMENT_REGION="$DETECTED_REGION"
  fi
fi

# Set deployment configuration from environment or defaults
export DEPLOYMENT_STAGE="${DEPLOYMENT_STAGE:-test}"
export STACK_DISAMBIGUATOR="${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
export DEPLOYMENT_REGION="${DEPLOYMENT_REGION:-$DEFAULT_REGION}"

echo "============================================="
echo "NovaAct Human Intervention - CDK Setup"
echo "============================================="
echo "CDK Entry Point: $CDK_APP_PATH"
echo ""
echo "Current Configuration:"
echo "  DEPLOYMENT_STAGE:       $DEPLOYMENT_STAGE"
echo "  STACK_DISAMBIGUATOR:    $STACK_DISAMBIGUATOR"
echo "  DEPLOYMENT_REGION:      $DEPLOYMENT_REGION"
echo "  DEPLOYMENT_ACCOUNT:     ${DEPLOYMENT_ACCOUNT:-<not detected - configure credentials>}"
echo ""

# Check if AWS CLI is installed
check_aws_cli() {
    echo "Checking AWS CLI installation..."
    if ! command -v aws &> /dev/null; then
        echo "❌ AWS CLI is not installed."
        echo ""
        echo "Please install AWS CLI first:"
        echo "  macOS: brew install awscli"
        echo "  Linux: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
    echo "✅ AWS CLI is installed: $(aws --version)"
    echo ""
}

# Check if Node.js and npm are installed
check_nodejs() {
    echo "Checking Node.js installation..."
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is not installed."
        echo ""
        echo "Please install Node.js 18+ first:"
        echo "  https://nodejs.org/"
        exit 1
    fi

    NODE_VERSION=$(node --version)
    echo "✅ Node.js is installed: $NODE_VERSION"

    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed."
        exit 1
    fi
    echo "✅ npm is installed: $(npm --version)"
    echo ""
}

# Check if CDK app entry point exists
check_cdk_app() {
    echo "Checking CDK application entry point..."
    if [ ! -f "$CDK_APP_PATH" ]; then
        echo "❌ CDK app not found at: $CDK_APP_PATH"
        echo "   Expected CDK entry point file is missing."
        return 1
    fi
    echo "✅ CDK app found: $CDK_APP_PATH"
    echo ""
    return 0
}

# Install or verify ts-node for CDK
check_ts_node() {
    echo "Checking ts-node (required for CDK TypeScript)..."
    if [ -d "node_modules" ] && [ -f "node_modules/.bin/ts-node" ]; then
        echo "✅ ts-node is available"
        echo ""
        return 0
    elif npm list ts-node &> /dev/null; then
        echo "✅ ts-node is installed"
        echo ""
        return 0
    else
        echo "⚠️  ts-node not found in dependencies"
        echo "   Installing ts-node as dev dependency..."
        npm install --save-dev ts-node
        echo "✅ ts-node installed"
        echo ""
        return 0
    fi
}

# Check current credentials
check_current_credentials() {
    echo "Checking current AWS credentials..."
    if aws sts get-caller-identity &> /dev/null; then
        CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
        CURRENT_USER=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null)
        CURRENT_REGION=$(aws configure get region 2>/dev/null || echo "not configured")

        echo "✅ AWS credentials are configured"
        if [ -n "$AWS_PROFILE" ]; then
            echo "   Profile: $AWS_PROFILE"
        fi
        echo "   Account: $CURRENT_ACCOUNT"
        echo "   Identity: $CURRENT_USER"
        echo "   Region: $CURRENT_REGION"
        echo ""

        # Set DEPLOYMENT_ACCOUNT if not already set
        if [ -z "$DEPLOYMENT_ACCOUNT" ]; then
            export DEPLOYMENT_ACCOUNT="$CURRENT_ACCOUNT"
        fi

        # Set DEPLOYMENT_REGION if not already set or if current region is not configured
        if [ -z "$DEPLOYMENT_REGION" ] || [ "$DEPLOYMENT_REGION" = "$DEFAULT_REGION" ]; then
            if [ "$CURRENT_REGION" != "not configured" ]; then
                export DEPLOYMENT_REGION="$CURRENT_REGION"
            fi
        fi

        return 0
    else
        echo "❌ No AWS credentials configured"
        echo ""
        return 1
    fi
}

# Guided first-time AWS user setup
guided_first_time_setup() {
    echo "============================================="
    echo "🎓 First-Time AWS User Setup Wizard"
    echo "============================================="
    echo ""
    echo "This wizard will help you set up AWS credentials for deployment."
    echo ""

    # Check if they already have credentials
    if aws sts get-caller-identity &> /dev/null; then
        CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
        CURRENT_USER=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null)

        echo "✅ AWS credentials are already configured!"
        echo "   Account: $CURRENT_ACCOUNT"
        echo "   Identity: $CURRENT_USER"
        echo ""

        read -p "Do you want to reconfigure with different credentials? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Using existing credentials."
            echo ""
            return 0
        fi
    fi

    echo "📚 First-Time AWS User Guide"
    echo ""
    echo "If you're new to AWS, you'll need to:"
    echo "  1. Create an AWS account (if you don't have one)"
    echo "  2. Create an IAM user for deployments"
    echo "  3. Create access keys for that user"
    echo "  4. Configure those credentials on this computer"
    echo ""
    echo "For detailed instructions, see:"
    echo "  - CLI-GUIDE.md (First-Time AWS User Setup section)"
    echo "  - https://docs.aws.amazon.com/IAM/latest/UserGuide/getting-started.html"
    echo ""

    read -p "Have you completed steps 1-3 above and have your access keys ready? (y/n): " -n 1 -r
    echo
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "No problem! Here's what you need to do:"
        echo ""
        echo "============================================="
        echo "📋 Step-by-Step Instructions"
        echo "============================================="
        echo ""
        echo "STEP 1: Create AWS Account (if you don't have one)"
        echo "  • Go to: https://aws.amazon.com/"
        echo "  • Click 'Create an AWS Account'"
        echo "  • Follow the registration process"
        echo "  • You'll need a credit card (but can use free tier)"
        echo ""
        echo "STEP 2: Sign In to AWS Console"
        echo "  • Go to: https://console.aws.amazon.com/"
        echo "  • Sign in with your root account email/password"
        echo ""
        echo "STEP 3: Create an IAM User for Deployment"
        echo "  • In AWS Console, search for 'IAM' and click it"
        echo "  • Click 'Users' in the left sidebar"
        echo "  • Click 'Create user'"
        echo "  • User name: cdk-deployer (or your choice)"
        echo "  • Click 'Next'"
        echo "  • Choose 'Attach policies directly'"
        echo "  • Search for and select 'AdministratorAccess'"
        echo "  • Click 'Next', then 'Create user'"
        echo ""
        echo "STEP 4: Create Access Keys"
        echo "  • Click on the user you just created"
        echo "  • Go to 'Security credentials' tab"
        echo "  • Scroll to 'Access keys' section"
        echo "  • Click 'Create access key'"
        echo "  • Select 'Command Line Interface (CLI)'"
        echo "  • Check the confirmation checkbox"
        echo "  • Click 'Next', then 'Create access key'"
        echo "  • ⚠️  SAVE THESE CREDENTIALS:"
        echo "    - Access Key ID (starts with AKIA...)"
        echo "    - Secret Access Key (long random string)"
        echo "  • Click 'Download .csv file' to save them"
        echo ""
        echo "STEP 5: Come Back Here"
        echo "  • Run this script again: ./setup-and-deploy.sh first-time-setup"
        echo "  • Or use interactive mode: ./setup-and-deploy.sh -i"
        echo "  • Select the option to configure credentials"
        echo ""
        echo "============================================="
        echo ""
        echo "📖 For detailed instructions with screenshots, see:"
        echo "   CLI-GUIDE.md → First-Time AWS User Setup"
        echo ""

        return 0
    fi

    echo "Great! Let's configure your AWS credentials."
    echo ""

    # Configure credentials
    configure_credentials_interactive

    # Verify they work
    if aws sts get-caller-identity &> /dev/null; then
        ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        USER_ARN=$(aws sts get-caller-identity --query Arn --output text)

        echo ""
        echo "============================================="
        echo "✅ Success! Your AWS credentials are configured!"
        echo "============================================="
        echo ""
        echo "Account: $ACCOUNT"
        echo "Identity: $USER_ARN"
        echo ""

        # Set environment variables
        export DEPLOYMENT_ACCOUNT="$ACCOUNT"

        echo "📋 Next Steps:"
        echo ""
        echo "1. Review deployment configuration:"
        echo "   ./setup-and-deploy.sh show-env"
        echo ""
        echo "2. Deploy with full workflow (recommended - detects and prompts for bootstrap):"
        echo "   ./setup-and-deploy.sh full"
        echo ""
        echo "   OR deploy step-by-step:"
        echo "   ./setup-and-deploy.sh bootstrap  # First-time setup only"
        echo "   ./setup-and-deploy.sh deploy     # Deploy all stacks"
        echo ""
        echo "💡 Tip: For detailed workflow examples, see CLI-GUIDE.md"
        echo ""

        read -p "Would you like to continue with the full deployment now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            echo "Starting full deployment workflow..."
            echo "This will detect if bootstrap is needed and prompt you."
            echo ""
            full_deployment
        fi
    else
        echo "❌ Credential verification failed."
        echo "   Please double-check your Access Key ID and Secret Access Key."
        echo "   You can try again by running: ./setup-and-deploy.sh configure"
    fi
}

# Display manual setup instructions
show_manual_setup() {
    echo "============================================="
    echo "Manual Credential Setup Instructions"
    echo "============================================="
    echo ""
    echo "You need to create AWS credentials with appropriate permissions."
    echo ""
    echo "📋 Steps to create credentials manually:"
    echo ""
    echo "1. Sign in to AWS Console as administrator:"
    echo "   https://console.aws.amazon.com/"
    echo ""
    echo "2. Navigate to IAM → Policies:"
    echo "   https://console.aws.amazon.com/iam/home#/policies"
    echo ""
    echo "3. Click 'Create policy' → Choose 'JSON' tab"
    echo "   - Copy the contents of: cdk-deployer-policy.json"
    echo "   - This file contains all required CDK deployment permissions"
    echo "   - Paste into the JSON editor"
    echo "   - Click 'Next'"
    echo "   - Policy name: NovaActHITL-CDK-Deployer-Policy"
    echo "   - Click 'Create policy'"
    echo ""
    echo "4. Navigate to IAM → Users:"
    echo "   https://console.aws.amazon.com/iam/home#/users"
    echo ""
    echo "5. Click 'Create user'"
    echo "   - User name: $IAM_USER_NAME (or your preferred name)"
    echo "   - Click Next"
    echo ""
    echo "6. Set permissions - Choose ONE option:"
    echo "   Option A (Quick): Attach 'AdministratorAccess' policy directly"
    echo "   Option B (Recommended): Attach 'NovaActHITL-CDK-Deployer-Policy' custom policy"
    echo ""
    echo "7. Click 'Create user'"
    echo ""
    echo "8. Create Access Key:"
    echo "   - Click on the created user"
    echo "   - Go to 'Security credentials' tab"
    echo "   - Click 'Create access key'"
    echo "   - Choose 'Command Line Interface (CLI)'"
    echo "   - Check the confirmation checkbox"
    echo "   - Click 'Create access key'"
    echo ""
    echo "9. Download or copy:"
    echo "   - Access Key ID"
    echo "   - Secret Access Key"
    echo "   ⚠️  Save these securely! You cannot retrieve the secret key later."
    echo ""
    echo "10. Run this script again with option 3 to configure the credentials"
    echo ""
    echo "📄 Policy File Location: ./cdk-deployer-policy.json"
    echo ""
}

# Create IAM user and access keys (requires admin credentials)
create_iam_user() {
    echo "============================================="
    echo "Creating IAM User via AWS CLI"
    echo "============================================="
    echo ""
    echo "This requires you to already have administrative credentials configured."
    echo ""

    # Verify we have credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo "❌ No AWS credentials found. Please configure credentials first."
        echo ""
        show_manual_setup
        return 1
    fi

    CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    echo "Current account: $CURRENT_ACCOUNT ✅"
    echo ""

    # Check if user already exists
    if aws iam get-user --user-name "$IAM_USER_NAME" &> /dev/null; then
        echo "⚠️  User '$IAM_USER_NAME' already exists."
        echo ""
        read -p "Do you want to create new access keys for this user? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    else
        echo "Creating IAM user: $IAM_USER_NAME"
        aws iam create-user --user-name "$IAM_USER_NAME"
        echo "✅ User created"
        echo ""

        # Ask which policy to attach
        echo "Which policy should be attached to this user?"
        echo "  1) AdministratorAccess (AWS managed, full access)"
        echo "  2) Custom CDK Deployer Policy (from cdk-deployer-policy.json, least privilege)"
        echo ""
        read -r -p "Choose (1 or 2): " policy_choice

        if [ "$policy_choice" = "2" ]; then
            # Create custom policy from JSON file
            if [ ! -f "cdk-deployer-policy.json" ]; then
                echo "❌ Policy file not found: cdk-deployer-policy.json"
                echo "   Falling back to AdministratorAccess"
                policy_choice="1"
            else
                POLICY_NAME="NovaActHITL-CDK-Deployer-Policy"
                echo "Creating custom IAM policy: $POLICY_NAME"

                # Check if policy already exists
                POLICY_ARN=$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='$POLICY_NAME'].Arn" --output text 2>/dev/null)

                if [ -z "$POLICY_ARN" ]; then
                    # Create new policy
                    POLICY_ARN=$(aws iam create-policy \
                        --policy-name "$POLICY_NAME" \
                        --policy-document file://cdk-deployer-policy.json \
                        --description "CDK deployment permissions for NovaAct HITL workflows" \
                        --query 'Policy.Arn' \
                        --output text)
                    echo "✅ Policy created: $POLICY_ARN"
                else
                    echo "✅ Using existing policy: $POLICY_ARN"
                fi

                echo "Attaching custom policy to user..."
                aws iam attach-user-policy \
                    --user-name "$IAM_USER_NAME" \
                    --policy-arn "$POLICY_ARN"
                echo "✅ Custom policy attached"
                echo ""
            fi
        fi

        if [ "$policy_choice" = "1" ] || [ "$policy_choice" != "2" ]; then
            echo "Attaching AdministratorAccess policy..."
            aws iam attach-user-policy \
                --user-name "$IAM_USER_NAME" \
                --policy-arn "arn:aws:iam::aws:policy/AdministratorAccess"
            echo "✅ AdministratorAccess policy attached"
            echo ""
        fi
    fi

    # Create access key
    echo "Creating access key..."
    ACCESS_KEY_OUTPUT=$(aws iam create-access-key --user-name "$IAM_USER_NAME" --output json)

    ACCESS_KEY_ID=$(echo "$ACCESS_KEY_OUTPUT" | grep -o '"AccessKeyId": "[^"]*' | cut -d'"' -f4)
    SECRET_ACCESS_KEY=$(echo "$ACCESS_KEY_OUTPUT" | grep -o '"SecretAccessKey": "[^"]*' | cut -d'"' -f4)

    echo ""
    echo "============================================="
    echo "✅ SUCCESS! Credentials Created"
    echo "============================================="
    echo ""
    echo "Access Key ID: $ACCESS_KEY_ID"
    echo "Secret Access Key: $SECRET_ACCESS_KEY"
    echo ""
    echo "⚠️  IMPORTANT: Save these credentials securely!"
    echo "   You will not be able to retrieve the secret key again."
    echo ""

    # Save to file
    CREDENTIALS_FILE="aws-credentials-$IAM_USER_NAME.txt"
    cat > "$CREDENTIALS_FILE" << EOF
AWS Credentials for HITL CDK Deployment
========================================
Created: $(date)
Account: $CURRENT_ACCOUNT
User: $IAM_USER_NAME

Access Key ID: $ACCESS_KEY_ID
Secret Access Key: $SECRET_ACCESS_KEY

Configuration Command:
aws configure

Enter these values when prompted:
- AWS Access Key ID: $ACCESS_KEY_ID
- AWS Secret Access Key: $SECRET_ACCESS_KEY
- Default region name: $DEFAULT_REGION
- Default output format: json
EOF

    echo "📄 Credentials saved to: $CREDENTIALS_FILE"
    echo ""

    read -p "Do you want to configure these credentials now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        configure_credentials_interactive "$ACCESS_KEY_ID" "$SECRET_ACCESS_KEY"
    fi
}

# Configure credentials interactively
configure_credentials_interactive() {
    local access_key="$1"
    local secret_key="$2"

    echo "============================================="
    echo "Configuring AWS Credentials"
    echo "============================================="
    echo ""

    # Ask for profile name
    local default_profile="hitl-deployer"
    echo "💡 Using AWS profiles allows you to maintain multiple sets of credentials."
    echo "   This won't overwrite your existing default AWS credentials."
    echo ""
    read -r -p "Enter AWS profile name [$default_profile]: " profile_name
    profile_name="${profile_name:-$default_profile}"
    echo ""

    if [ -z "$access_key" ]; then
        read -r -p "Enter AWS Access Key ID: " access_key
    fi

    if [ -z "$secret_key" ]; then
        read -r -sp "Enter AWS Secret Access Key: " secret_key
        echo ""
    fi

    echo ""
    echo "Creating AWS profile: $profile_name"

    # Use aws configure to set credentials with profile
    aws configure set aws_access_key_id "$access_key" --profile "$profile_name"
    aws configure set aws_secret_access_key "$secret_key" --profile "$profile_name"
    aws configure set region "$DEFAULT_REGION" --profile "$profile_name"
    aws configure set output "json" --profile "$profile_name"

    echo "✅ Credentials configured for profile: $profile_name"
    echo ""

    # Set AWS_PROFILE for this session and verification
    export AWS_PROFILE="$profile_name"

    # Verify
    echo "Verifying credentials..."
    if aws sts get-caller-identity &> /dev/null; then
        ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        USER_ARN=$(aws sts get-caller-identity --query Arn --output text)

        echo "✅ Credentials verified successfully!"
        echo "   Profile: $profile_name"
        echo "   Account: $ACCOUNT"
        echo "   Identity: $USER_ARN"
        echo ""

        # Set DEPLOYMENT_ACCOUNT if not already set
        if [ -z "$DEPLOYMENT_ACCOUNT" ]; then
            export DEPLOYMENT_ACCOUNT="$ACCOUNT"
        fi

        # Keep existing DEPLOYMENT_REGION or use default
        if [ -z "$DEPLOYMENT_REGION" ]; then
            export DEPLOYMENT_REGION="$DEFAULT_REGION"
        fi

        echo "============================================="
        echo "📋 To use this profile in future sessions:"
        echo "============================================="
        echo ""
        echo "Option 1: Export before running the script"
        echo "  export AWS_PROFILE=$profile_name"
        echo "  ./setup-and-deploy.sh deploy"
        echo ""
        echo "Option 2: Set for current shell session only"
        echo "  AWS_PROFILE=$profile_name ./setup-and-deploy.sh deploy"
        echo ""
        echo "Option 3: Add to your shell profile (~/.bashrc or ~/.zshrc)"
        echo "  echo 'export AWS_PROFILE=$profile_name' >> ~/.bashrc"
        echo ""
        echo "Note: AWS_PROFILE is currently set to '$profile_name' for this session."
        echo ""
    else
        echo "❌ Credential verification failed. Please check your credentials."
        unset AWS_PROFILE
        return 1
    fi
}

# Set deployment environment variables
configure_deployment_env() {
    echo "============================================="
    echo "Configure Deployment Environment"
    echo "============================================="
    echo ""

    echo "Current settings:"
    echo "  DEPLOYMENT_STAGE:       $DEPLOYMENT_STAGE"
    echo "  STACK_DISAMBIGUATOR:    $STACK_DISAMBIGUATOR"
    echo "  DEPLOYMENT_REGION:      $DEPLOYMENT_REGION"
    echo "  DEPLOYMENT_ACCOUNT:     ${DEPLOYMENT_ACCOUNT:-<not set>}"
    echo ""

    read -r -p "Deployment stage (dev/staging/prod) [$DEPLOYMENT_STAGE]: " input_stage
    if [ -n "$input_stage" ]; then
        export DEPLOYMENT_STAGE="$input_stage"
    fi

    read -r -p "Stack Disambiguator (unique identifier) [$STACK_DISAMBIGUATOR]: " input_disambiguator
    if [ -n "$input_disambiguator" ]; then
        export STACK_DISAMBIGUATOR="$input_disambiguator"
    fi

    read -r -p "AWS Region [$DEPLOYMENT_REGION]: " input_region
    if [ -n "$input_region" ]; then
        export DEPLOYMENT_REGION="$input_region"
        # Update region in AWS profile if AWS_PROFILE is set
        if [ -n "$AWS_PROFILE" ]; then
            aws configure set region "$input_region" --profile "$AWS_PROFILE"
        else
            aws configure set region "$input_region"
        fi
    fi

    echo ""
    echo "✅ Environment configured:"
    echo ""
    echo "To use these settings in future runs, export them before running the script:"
    if [ -n "$AWS_PROFILE" ]; then
        echo "   export AWS_PROFILE=$AWS_PROFILE"
    fi
    echo "   export DEPLOYMENT_STAGE=$DEPLOYMENT_STAGE"
    echo "   export STACK_DISAMBIGUATOR=$STACK_DISAMBIGUATOR"
    echo "   export DEPLOYMENT_REGION=$DEPLOYMENT_REGION"
    echo "   export DEPLOYMENT_ACCOUNT=$DEPLOYMENT_ACCOUNT"
    echo ""
}

# Install dependencies
install_dependencies() {
    echo "============================================="
    echo "Installing Dependencies"
    echo "============================================="
    echo ""

    if [ ! -d "node_modules" ]; then
        echo "Running npm install..."
        npm install
        echo "✅ Dependencies installed"
    else
        if [ -n "$NON_INTERACTIVE" ]; then
            echo "✅ Dependencies already installed (skipping)"
        else
            read -p "node_modules exists. Reinstall? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Running npm install..."
                npm install
                echo "✅ Dependencies installed"
            fi
        fi
    fi
    echo ""
}

# Build the project
build_project() {
    echo "============================================="
    echo "Building Project"
    echo "============================================="
    echo ""

    echo "Running npm run build..."
    npm run build
    echo "✅ Build completed"
    echo ""
}

# Check if CDK is bootstrapped in the target region
check_bootstrap_needed() {
    local account="$1"
    local region="$2"

    if [ -z "$account" ] || [ -z "$region" ]; then
        echo "❌ Account and region required for bootstrap check"
        return 1
    fi

    # Check if CDKToolkit stack exists
    if aws cloudformation describe-stacks \
        --stack-name CDKToolkit \
        --region "$region" \
        --query 'Stacks[0].StackStatus' \
        --output text &>/dev/null; then
        return 1  # Bootstrap NOT needed (stack exists)
    else
        return 0  # Bootstrap IS needed (stack doesn't exist)
    fi
}

# Check if this is a first-time deployment of our stacks
is_first_time_deployment() {
    local disambiguator="$1"
    local region="${2:-$DEPLOYMENT_REGION}"

    if [ -z "$disambiguator" ]; then
        echo "❌ Disambiguator required for first-time deployment check"
        return 1
    fi

    # Check if the Storage stack exists (first stack to be deployed)
    if aws cloudformation describe-stacks \
        --stack-name "NovaActHITL-Storage-${disambiguator}" \
        --region "$region" \
        --query 'Stacks[0].StackStatus' \
        --output text &>/dev/null; then
        return 1  # NOT first time (stack exists)
    else
        return 0  # IS first time (stack doesn't exist)
    fi
}

# Check for failed stacks that need cleanup
check_failed_stacks() {
    local disambiguator="$1"
    local region="${2:-$DEPLOYMENT_REGION}"

    if [ -z "$disambiguator" ]; then
        return 0  # Skip check if no disambiguator
    fi

    # Check if Storage stack exists in a failed state
    local stack_status
    stack_status=$(aws cloudformation describe-stacks \
        --stack-name "NovaActHITL-Storage-${disambiguator}" \
        --region "$region" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null)

    if [ "$stack_status" = "ROLLBACK_COMPLETE" ] || [ "$stack_status" = "ROLLBACK_FAILED" ]; then
        echo "⚠️  Found stack in failed state: NovaActHITL-Storage-${disambiguator} (${stack_status})"
        echo ""
        echo "This stack cannot be updated and must be deleted before redeploying."
        echo ""
        read -p "Delete the failed stack and continue? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Deleting stack NovaActHITL-Storage-${disambiguator}..."
            aws cloudformation delete-stack \
                --stack-name "NovaActHITL-Storage-${disambiguator}" \
                --region "$region"

            echo "Waiting for stack deletion to complete..."
            aws cloudformation wait stack-delete-complete \
                --stack-name "NovaActHITL-Storage-${disambiguator}" \
                --region "$region"

            echo "✅ Stack deleted successfully"
            echo ""
            return 0
        else
            echo ""
            echo "❌ Cannot deploy with existing failed stack."
            echo "   Please delete manually or use a different STACK_DISAMBIGUATOR."
            echo ""
            echo "   To delete manually:"
            echo "   aws cloudformation delete-stack --stack-name NovaActHITL-Storage-${disambiguator} --region ${region}"
            return 1
        fi
    fi

    return 0  # No failed stacks found
}

# Bootstrap CDK
bootstrap_cdk() {
    echo "============================================="
    echo "Bootstrapping CDK"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    echo "Bootstrapping CDK in account $DEPLOYMENT_ACCOUNT, region $DEPLOYMENT_REGION..."
    npx cdk bootstrap "aws://$DEPLOYMENT_ACCOUNT/$DEPLOYMENT_REGION"
    echo "✅ CDK bootstrapped"
    echo ""
}

# List CDK stacks
list_stacks() {
    echo "============================================="
    echo "Available CDK Stacks"
    echo "============================================="
    echo ""
    echo "The following stacks will be created:"
    echo "  1. NovaActHITL-Storage-${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
    echo "  2. NovaActHITL-Approval-${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
    echo "  3. NovaActHITL-UITakeover-${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
    echo "  4. NovaActHITL-WebSocket-${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
    echo ""
    echo "Running 'cdk list' to confirm..."
    npx cdk list
    echo ""
}

# Configure Slack secrets in Secrets Manager
configure_slack_secrets() {
    echo "============================================="
    echo "Configure Slack Bot Tokens"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    local disambiguator="${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
    local secret_name="nova-act-slack-secrets-${disambiguator}"

    # Check if secret exists
    if ! aws secretsmanager describe-secret --secret-id "$secret_name" --region "$DEPLOYMENT_REGION" &> /dev/null; then
        echo "❌ Secret not found: $secret_name"
        echo "   Make sure the Storage stack is deployed first."
        return 1
    fi

    echo "This will configure Slack bot tokens for human intervention notifications."
    echo ""
    echo "Secret: $secret_name"
    echo "Region: $DEPLOYMENT_REGION"
    echo ""
    echo "💡 Tip: You can enter the same token for both if using a single Slack app."
    echo ""

    # Prompt for Approval workflow token
    local approval_token=""
    read -r -sp "Enter Slack bot token for Approval workflow (starts with xoxb-): " approval_token
    echo ""

    if [ -z "$approval_token" ]; then
        echo "❌ Token cannot be empty"
        return 1
    fi

    # Prompt for UITakeover workflow token
    echo ""
    local uitakeover_token=""
    read -r -sp "Enter Slack bot token for UITakeover workflow (starts with xoxb-): " uitakeover_token
    echo ""

    if [ -z "$uitakeover_token" ]; then
        echo "❌ Token cannot be empty"
        return 1
    fi

    # Create JSON structure
    local secret_json
    secret_json=$(cat <<EOF
{
  "UITakeover": "$uitakeover_token",
  "Approval": "$approval_token"
}
EOF
)

    echo ""
    echo "Updating secret in AWS Secrets Manager..."

    if aws secretsmanager put-secret-value \
        --secret-id "$secret_name" \
        --secret-string "$secret_json" \
        --region "$DEPLOYMENT_REGION" &> /dev/null; then

        echo "✅ Slack bot tokens configured successfully!"
        echo ""
        echo "Secret: $secret_name"
        echo "Region: $DEPLOYMENT_REGION"
        echo ""
        echo "Your Lambda functions will now be able to send Slack notifications."
    else
        echo "❌ Failed to update secret"
        echo "   Please check your AWS permissions for Secrets Manager"
        return 1
    fi
    echo ""
}

# Configure SES email identities
configure_email_identities() {
    echo "============================================="
    echo "Configure SES Email Identities"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    echo "This will configure email identities in AWS SES for notifications."
    echo ""
    echo "Region: $DEPLOYMENT_REGION"
    echo ""
    echo "You need to verify TWO email addresses:"
    echo "  1. FROM address - The sender email for notifications"
    echo "  2. TO address   - The recipient email for notifications"
    echo ""
    echo "⚠️  Important: You'll receive verification emails at both addresses."
    echo "   Click the verification links to activate them."
    echo ""

    # Get FROM email
    read -r -p "Enter FROM email address (sender): " from_email
    if [ -z "$from_email" ]; then
        echo "❌ FROM email cannot be empty"
        return 1
    fi

    # Validate email format (basic check)
    if ! echo "$from_email" | grep -qE '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'; then
        echo "❌ Invalid email format: $from_email"
        return 1
    fi

    # Get TO email
    read -r -p "Enter TO email address (recipient): " to_email
    if [ -z "$to_email" ]; then
        echo "❌ TO email cannot be empty"
        return 1
    fi

    # Validate email format (basic check)
    if ! echo "$to_email" | grep -qE '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'; then
        echo "❌ Invalid email format: $to_email"
        return 1
    fi

    echo ""
    echo "Creating email identities in SES..."
    echo ""

    # Create FROM email identity
    echo "Setting up FROM address: $from_email"

    # Check if identity already exists
    local from_status
    from_status=$(aws ses get-identity-verification-attributes \
        --identities "$from_email" \
        --region "$DEPLOYMENT_REGION" \
        --query "VerificationAttributes.\"$from_email\".VerificationStatus" \
        --output text 2>/dev/null)

    if [ -n "$from_status" ] && [ "$from_status" != "None" ]; then
        # Identity already exists
        if [ "$from_status" = "Success" ]; then
            echo "✅ Already verified: $from_email"
        else
            echo "⏳ Already exists (status: $from_status): $from_email"
            echo "   Check your inbox for the verification email"
        fi
    else
        # Identity doesn't exist, create it
        if aws ses verify-email-identity --email-address "$from_email" --region "$DEPLOYMENT_REGION" 2>/dev/null; then
            echo "✅ Verification email sent to: $from_email"
        else
            echo "❌ Failed to create identity for: $from_email"
            return 1
        fi
    fi

    echo ""

    # Create TO email identity
    echo "Setting up TO address: $to_email"

    # Check if identity already exists
    local to_status
    to_status=$(aws ses get-identity-verification-attributes \
        --identities "$to_email" \
        --region "$DEPLOYMENT_REGION" \
        --query "VerificationAttributes.\"$to_email\".VerificationStatus" \
        --output text 2>/dev/null)

    if [ -n "$to_status" ] && [ "$to_status" != "None" ]; then
        # Identity already exists
        if [ "$to_status" = "Success" ]; then
            echo "✅ Already verified: $to_email"
        else
            echo "⏳ Already exists (status: $to_status): $to_email"
            echo "   Check your inbox for the verification email"
        fi
    else
        # Identity doesn't exist, create it
        if aws ses verify-email-identity --email-address "$to_email" --region "$DEPLOYMENT_REGION" 2>/dev/null; then
            echo "✅ Verification email sent to: $to_email"
        else
            echo "❌ Failed to create identity for: $to_email"
            return 1
        fi
    fi

    echo ""
    echo "============================================="
    echo "✅ Email identities configured!"
    echo "============================================="
    echo ""
    echo "Next steps:"
    echo "  1. Check the inboxes for both email addresses"
    echo "  2. Click the verification links in the emails from AWS"
    echo "  3. Wait a few minutes for verification to complete"
    echo ""
    echo "To check verification status:"
    echo "  ./setup-and-deploy.sh check-email-status"
    echo ""
    echo "Configured identities:"
    echo "  FROM: $from_email"
    echo "  TO:   $to_email"
    echo ""
}

# Check SES email verification status
check_email_status() {
    echo "============================================="
    echo "Check SES Email Verification Status"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    echo "Region: $DEPLOYMENT_REGION"
    echo ""
    echo "Checking all email identities..."
    echo ""

    # Get all identities (filter out the "IDENTITIES" label from output)
    local identities
    identities=$(aws ses list-identities --region "$DEPLOYMENT_REGION" --output text 2>/dev/null | awk '{print $2}')

    if [ -z "$identities" ]; then
        echo "No email identities found in SES."
        echo ""
        echo "Run './setup-and-deploy.sh configure-email' to set up identities."
        return 0
    fi

    # Check each identity
    for email in $identities; do
        local status
        status=$(aws ses get-identity-verification-attributes \
            --identities "$email" \
            --region "$DEPLOYMENT_REGION" \
            --query "VerificationAttributes.\"$email\".VerificationStatus" \
            --output text 2>/dev/null)

        if [ "$status" = "Success" ]; then
            echo "✅ $email - Verified"
        elif [ "$status" = "Pending" ]; then
            echo "⏳ $email - Pending (check inbox for verification email)"
        else
            echo "❌ $email - Not verified"
        fi
    done

    echo ""
    echo "Note: If emails are pending, click the verification links sent to your inbox."
    echo ""
}

# Show stack outputs
show_stack_outputs() {
    echo "============================================="
    echo "Deployed Stack Outputs"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    local stack_prefix="NovaActHITL"
    local disambiguator="${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"

    echo "Fetching stack outputs for disambiguator: $disambiguator"
    echo ""

    for stack_type in Storage Approval UITakeover WebSocket; do
        local stack_name="${stack_prefix}-${stack_type}-${disambiguator}"
        echo "--- $stack_name ---"

        if aws cloudformation describe-stacks --stack-name "$stack_name" --region "$DEPLOYMENT_REGION" &> /dev/null; then
            aws cloudformation describe-stacks \
                --stack-name "$stack_name" \
                --region "$DEPLOYMENT_REGION" \
                --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue,Description]' \
                --output table 2>/dev/null || echo "No outputs available"
        else
            echo "Stack not found or not deployed"
        fi
        echo ""
    done
}

# Show client environment variables for usage examples
show_client_env_vars() {
    echo "============================================="
    echo "Client Environment Variables"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    local disambiguator="${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
    local stack_prefix="NovaActHITL"

    echo "Fetching values for disambiguator: $disambiguator"
    echo ""

    # Get WebSocket endpoint
    local websocket_endpoint
    websocket_endpoint=$(aws cloudformation describe-stacks \
        --stack-name "${stack_prefix}-WebSocket-${disambiguator}" \
        --region "$DEPLOYMENT_REGION" \
        --query "Stacks[0].Outputs[?OutputKey==\`WebSocketEndpoint\`].OutputValue" \
        --output text 2>/dev/null)

    # Get Execution Role ARN
    local execution_role_arn
    execution_role_arn=$(aws cloudformation describe-stacks \
        --stack-name "${stack_prefix}-WebSocket-${disambiguator}" \
        --region "$DEPLOYMENT_REGION" \
        --query "Stacks[0].Outputs[?OutputKey==\`ExecutionRoleArn\`].OutputValue" \
        --output text 2>/dev/null)

    # Get Screenshot S3 Bucket
    local screenshot_bucket
    screenshot_bucket=$(aws cloudformation describe-stacks \
        --stack-name "${stack_prefix}-Approval-${disambiguator}" \
        --region "$DEPLOYMENT_REGION" \
        --query "Stacks[0].Outputs[?OutputKey==\`ScreenshotBucketName\`].OutputValue" \
        --output text 2>/dev/null)

    if [ -z "$websocket_endpoint" ] || [ -z "$execution_role_arn" ]; then
        echo "❌ Could not fetch all required values. Make sure the stacks are deployed."
        echo ""
        echo "Missing values:"
        [ -z "$websocket_endpoint" ] && echo "  - WebSocket endpoint (WebSocket stack)"
        [ -z "$execution_role_arn" ] && echo "  - Execution role ARN (WebSocket stack)"
        [ -z "$screenshot_bucket" ] && echo "  - Screenshot bucket (Approval stack - optional)"
        return 1
    fi

    echo "============================================="
    echo "Environment Variables for Client Scripts"
    echo "============================================="
    echo ""
    echo "Copy these values to your client script or export them:"
    echo ""
    echo "# Python script assignment:"
    echo "HITL_EXECUTOR_ENDPOINT = \"$websocket_endpoint\""
    echo "HITL_IAM_ROLE_ARN = \"$execution_role_arn\""
    if [ -n "$screenshot_bucket" ]; then
        echo "HITL_SCREENSHOT_S3_BUCKET = \"$screenshot_bucket\""
    else
        echo "HITL_SCREENSHOT_S3_BUCKET = \"\"  # Optional - only for Approval workflow"
    fi
    echo "AWS_REGION = \"$DEPLOYMENT_REGION\""
    echo ""
    echo "# Shell export commands:"
    echo "export HITL_EXECUTOR_ENDPOINT=\"$websocket_endpoint\""
    echo "export HITL_IAM_ROLE_ARN=\"$execution_role_arn\""
    if [ -n "$screenshot_bucket" ]; then
        echo "export HITL_SCREENSHOT_S3_BUCKET=\"$screenshot_bucket\""
    else
        echo "export HITL_SCREENSHOT_S3_BUCKET=\"\"  # Optional - only for Approval workflow"
    fi
    echo "export AWS_REGION=\"$DEPLOYMENT_REGION\""
    echo ""
    echo "============================================="
    echo ""
}

# Prepare stacks (install + build + synth)
prepare_stacks() {
    echo "============================================="
    echo "Preparing Stacks (Install + Build + Synth)"
    echo "============================================="
    echo ""

    # Install dependencies
    if [ ! -d "node_modules" ]; then
        echo "Step 1/3: Installing dependencies..."
        npm install
        echo "✅ Dependencies installed"
    else
        echo "Step 1/3: Dependencies already installed (skipping)"
    fi
    echo ""

    # Build project
    echo "Step 2/3: Building project..."
    npm run build
    echo "✅ Build completed"
    echo ""

    # Synthesize stacks
    echo "Step 3/3: Synthesizing CDK stacks..."
    npx cdk synth
    echo "✅ Synthesis completed"
    echo ""

    echo "============================================="
    echo "✅ Stack preparation complete!"
    echo "============================================="
    echo ""
}

# Synthesize CDK stacks
synth_stacks() {
    echo "============================================="
    echo "Synthesizing CDK Stacks"
    echo "============================================="
    echo ""

    npx cdk synth
    echo ""
}

# Diff CDK stacks
diff_stacks() {
    echo "============================================="
    echo "Checking Stack Differences"
    echo "============================================="
    echo ""

    npx cdk diff
    echo ""
}

# Deploy CDK stacks
deploy_stacks() {
    echo "============================================="
    echo "Deploying CDK Stacks"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    # Check for failed stacks that need cleanup
    check_failed_stacks "$STACK_DISAMBIGUATOR" "$DEPLOYMENT_REGION" || {
        return 1
    }

    # Check if CDK is bootstrapped
    if check_bootstrap_needed "$DEPLOYMENT_ACCOUNT" "$DEPLOYMENT_REGION"; then
        echo "⚠️  CDK is not bootstrapped in $DEPLOYMENT_REGION"
        echo ""
        echo "CDK bootstrap is required for first-time deployment."
        echo "This creates necessary resources (S3 bucket, ECR repository, IAM roles, etc.)"
        echo ""
        read -p "Would you like to bootstrap now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            bootstrap_cdk || {
                echo "❌ Bootstrap failed"
                return 1
            }
        else
            echo ""
            echo "❌ Cannot deploy without bootstrapping"
            echo "   Run: ./setup-and-deploy.sh bootstrap"
            return 1
        fi
        echo ""
    fi

    # Check if this is first-time deployment of our stacks
    if is_first_time_deployment "$STACK_DISAMBIGUATOR" "$DEPLOYMENT_REGION"; then
        echo "🆕 First-time deployment detected for disambiguator: $STACK_DISAMBIGUATOR"
        echo ""
    fi

    echo "Deployment Configuration:"
    echo "  DEPLOYMENT_ACCOUNT:     $DEPLOYMENT_ACCOUNT"
    echo "  DEPLOYMENT_REGION:      $DEPLOYMENT_REGION"
    echo "  DEPLOYMENT_STAGE:       $DEPLOYMENT_STAGE"
    echo "  STACK_DISAMBIGUATOR:    $STACK_DISAMBIGUATOR"
    echo ""

    read -p "Deploy all stacks? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        npx cdk deploy --all --require-approval never
        echo ""
        echo "✅ Deployment completed!"
        echo ""

        # Show stack outputs
        read -p "Show stack outputs? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            show_stack_outputs
        fi

        # Prompt to configure Slack secrets
        echo ""
        read -p "Configure Slack bot tokens now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            configure_slack_secrets
        else
            echo ""
            echo "💡 You can configure Slack tokens later with:"
            echo "   ./setup-and-deploy.sh configure-slack-secrets"
            echo "   OR interactive mode option 19"
        fi

        # Prompt to configure email identities
        echo ""
        read -p "Configure SES email identities now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            configure_email_identities
        else
            echo ""
            echo "💡 You can configure email identities later with:"
            echo "   ./setup-and-deploy.sh configure-email"
            echo "   OR interactive mode option 20"
        fi

        echo ""
        echo "To view your stacks:"
        echo "  aws cloudformation list-stacks --region $DEPLOYMENT_REGION"
    fi
    echo ""
}

# Deploy individual stack
deploy_individual_stack() {
    echo "============================================="
    echo "Deploy Individual Stack"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    local disambiguator="${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"

    echo "Available stacks:"
    echo "  1. NovaActHITL-Storage-$disambiguator"
    echo "  2. NovaActHITL-Approval-$disambiguator"
    echo "  3. NovaActHITL-UITakeover-$disambiguator"
    echo "  4. NovaActHITL-WebSocket-$disambiguator"
    echo ""

    read -r -p "Enter stack number (1-4) or full stack name: " choice

    local stack_name=""
    case $choice in
        1)
            stack_name="NovaActHITL-Storage-$disambiguator"
            ;;
        2)
            stack_name="NovaActHITL-Approval-$disambiguator"
            ;;
        3)
            stack_name="NovaActHITL-UITakeover-$disambiguator"
            ;;
        4)
            stack_name="NovaActHITL-WebSocket-$disambiguator"
            ;;
        *)
            stack_name="$choice"
            ;;
    esac

    echo ""
    echo "Deploying stack: $stack_name"
    echo ""

    npx cdk deploy "$stack_name" --require-approval never
    echo ""
    echo "✅ Stack deployed: $stack_name"
    echo ""
}

# Quick deploy (skip prompts)
quick_deploy() {
    echo "============================================="
    echo "Quick Deploy (No Prompts)"
    echo "============================================="
    echo ""

    if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
        check_current_credentials || {
            echo "❌ Please configure credentials first"
            return 1
        }
    fi

    # Check for failed stacks that need cleanup
    check_failed_stacks "$STACK_DISAMBIGUATOR" "$DEPLOYMENT_REGION" || {
        return 1
    }

    # Check if CDK is bootstrapped
    if check_bootstrap_needed "$DEPLOYMENT_ACCOUNT" "$DEPLOYMENT_REGION"; then
        echo "⚠️  CDK is not bootstrapped in $DEPLOYMENT_REGION"
        echo ""
        echo "CDK bootstrap is required for first-time deployment."
        echo "This creates necessary resources (S3 bucket, ECR repository, IAM roles, etc.)"
        echo ""
        read -p "Bootstrap CDK now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            bootstrap_cdk || {
                echo "❌ Bootstrap failed"
                return 1
            }
        else
            echo "❌ Cannot deploy without bootstrapping. Exiting."
            return 1
        fi
    fi

    # Check if this is first-time deployment of our stacks
    if is_first_time_deployment "$STACK_DISAMBIGUATOR" "$DEPLOYMENT_REGION"; then
        echo "🆕 First-time deployment detected for disambiguator: $STACK_DISAMBIGUATOR"
        echo ""
    fi

    echo "Deployment Configuration:"
    echo "  DEPLOYMENT_ACCOUNT:     $DEPLOYMENT_ACCOUNT"
    echo "  DEPLOYMENT_REGION:      $DEPLOYMENT_REGION"
    echo "  DEPLOYMENT_STAGE:       $DEPLOYMENT_STAGE"
    echo "  STACK_DISAMBIGUATOR:    $STACK_DISAMBIGUATOR"
    echo ""

    echo "Building project..."
    npm run build

    echo ""
    echo "Deploying all stacks..."
    npx cdk deploy --all --require-approval never

    echo ""
    echo "✅ Quick deployment completed!"
    echo ""

    show_stack_outputs

    # Prompt to configure Slack secrets and email identities
    if [ -z "$NON_INTERACTIVE" ]; then
        echo ""
        read -p "Configure Slack bot tokens now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            configure_slack_secrets
        else
            echo ""
            echo "💡 You can configure Slack tokens later with:"
            echo "   ./setup-and-deploy.sh configure-slack-secrets"
        fi

        echo ""
        read -p "Configure SES email identities now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            configure_email_identities
        else
            echo ""
            echo "💡 You can configure email identities later with:"
            echo "   ./setup-and-deploy.sh configure-email"
        fi
    else
        echo ""
        echo "💡 Remember to configure notifications:"
        echo "   ./setup-and-deploy.sh configure-slack-secrets  # Slack tokens"
        echo "   ./setup-and-deploy.sh configure-email           # SES emails"
    fi
}

# Display current environment configuration
show_env_config() {
    echo "============================================="
    echo "Current Environment Configuration"
    echo "============================================="
    echo ""
    echo "Environment Variables:"
    if [ -n "$AWS_PROFILE" ]; then
        echo "  AWS_PROFILE:            $AWS_PROFILE"
    else
        echo "  AWS_PROFILE:            <not set - using default>"
    fi
    echo "  DEPLOYMENT_STAGE:       $DEPLOYMENT_STAGE"
    echo "  STACK_DISAMBIGUATOR:    $STACK_DISAMBIGUATOR"
    echo "  DEPLOYMENT_REGION:      $DEPLOYMENT_REGION"
    echo "  DEPLOYMENT_ACCOUNT:     ${DEPLOYMENT_ACCOUNT:-<not set>}"
    echo ""
    echo "Stack Names:"
    echo "  1. NovaActHITL-Storage-$STACK_DISAMBIGUATOR"
    echo "  2. NovaActHITL-Approval-$STACK_DISAMBIGUATOR"
    echo "  3. NovaActHITL-UITakeover-$STACK_DISAMBIGUATOR"
    echo "  4. NovaActHITL-WebSocket-$STACK_DISAMBIGUATOR"
    echo ""
    echo "To set these variables for future runs:"
    if [ -n "$AWS_PROFILE" ]; then
        echo "  export AWS_PROFILE=$AWS_PROFILE"
    fi
    echo "  export DEPLOYMENT_STAGE=$DEPLOYMENT_STAGE"
    echo "  export STACK_DISAMBIGUATOR=$STACK_DISAMBIGUATOR"
    echo "  export DEPLOYMENT_REGION=$DEPLOYMENT_REGION"
    if [ -n "$DEPLOYMENT_ACCOUNT" ]; then
        echo "  export DEPLOYMENT_ACCOUNT=$DEPLOYMENT_ACCOUNT"
    fi
    echo ""
}

# Destroy CDK stacks
destroy_stacks() {
    echo "============================================="
    echo "⚠️  DESTROY CDK Stacks"
    echo "============================================="
    echo ""
    echo "This will DELETE all resources created by the CDK stacks!"
    echo ""

    if [ -n "$NON_INTERACTIVE" ]; then
        echo "⚠️  Non-interactive mode: Destroying without confirmation"
        npx cdk destroy --all --force
        echo ""
        echo "✅ Stacks destroyed"
    else
        read -p "Are you sure you want to destroy all stacks? (yes/no): " -r
        echo
        if [[ $REPLY == "yes" ]]; then
            npx cdk destroy --all
            echo ""
            echo "✅ Stacks destroyed"
        else
            echo "❌ Destroy cancelled"
        fi
    fi
    echo ""
}

# Show usage information
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS] [COMMAND]

NovaAct Human Intervention - CDK Setup and Deployment Script

OPTIONS:
  -s, --stage STAGE          Deployment stage (overrides DEPLOYMENT_STAGE env var)
  -d, --disambiguator VALUE  Stack disambiguator (overrides STACK_DISAMBIGUATOR env var)
  -r, --region REGION        AWS region (overrides DEPLOYMENT_REGION env var)
  -a, --account ACCOUNT      AWS account ID (overrides DEPLOYMENT_ACCOUNT env var)
  -i, --interactive          Run in interactive menu mode

Note: Command-line options override environment variables

MODES:
  Default Mode:        $0
                      (no arguments - runs check-credentials)

  Interactive Mode:    $0 -i
                      $0 --interactive
                      (shows interactive menu)

  Command Mode:        $0 [OPTIONS] COMMAND
                      (execute specific commands with optional overrides)

SETUP COMMANDS:
  first-time-setup   🎓 Guided setup wizard for first-time AWS users (START HERE!)
  check-credentials  Check current AWS credentials status
  configure          Configure AWS credentials interactively
  create-user        Create new IAM user and access keys
  show-setup         Show manual setup instructions
  show-env           Show current environment configuration
  configure-env      Configure deployment environment variables

BUILD & DEPLOY COMMANDS:
  prepare            Prepare stacks (install + build + synth)
  install            Install dependencies (npm install)
  build              Build project (npm run build)
  bootstrap          Bootstrap CDK (first time setup)
  list               List available stacks
  synth              Synthesize stacks (cdk synth)
  diff               Check stack differences (cdk diff)
  deploy             Deploy all stacks
  deploy-stack NAME  Deploy individual stack by name
  quick-deploy       Quick deploy (build + deploy, no prompts)
  full               Full deployment workflow (all steps)

MANAGE & MONITOR COMMANDS:
  outputs                 Show deployed stack outputs
  client-env              Show client environment variables for usage examples
  configure-slack-secrets Configure Slack bot tokens in Secrets Manager
  configure-email         Configure SES email identities (FROM and TO addresses)
  check-email-status      Check SES email verification status
  verify                  Verify CDK deployment readiness
  destroy                 Destroy all stacks (⚠️  DANGER)

GENERAL COMMANDS:
  help, --help, -h   Show this help message

ENVIRONMENT VARIABLES:
  AWS_PROFILE            AWS CLI profile to use (e.g., hitl-deployer)
  DEPLOYMENT_STAGE       Deployment stage (default: test)
  STACK_DISAMBIGUATOR    Unique stack identifier (default: same as DEPLOYMENT_STAGE)
  DEPLOYMENT_REGION      AWS region (default: us-east-1)
  DEPLOYMENT_ACCOUNT     AWS account ID (auto-detected from credentials)

EXAMPLES:
  # First-time AWS user? Start here!
  $0 first-time-setup

  # Quick credential check (default)
  $0

  # Interactive mode (shows menu)
  $0 -i
  $0 --interactive

  # Prepare and deploy in one go
  $0 prepare && $0 deploy

  # Quick deployment
  $0 quick-deploy

  # Deploy with custom configuration using environment variables
  export DEPLOYMENT_STAGE=prod
  export DEPLOYMENT_REGION=us-west-2
  $0 full

  # Deploy with custom configuration using command-line options
  $0 -s prod -r us-west-2 full
  $0 --stage prod --region us-west-2 deploy

  # Deploy to a specific stage and region with disambiguator
  $0 -s prod -d prod-alpha -r us-west-2 deploy

  # Quick deploy to dev in us-east-1
  $0 --stage dev --region us-east-1 quick-deploy

  # Check what will change with specific stage
  $0 -s staging diff

  # Deploy individual stack with custom stage
  $0 -s dev deploy-stack NovaActHITL-Storage-dev

  # Mix environment variables and command-line options (options override env)
  export DEPLOYMENT_STAGE=dev
  $0 -s prod deploy  # Will use prod, not dev

EOF
}

# Verify CDK readiness
verify_cdk_ready() {
    echo "============================================="
    echo "Verifying CDK Deployment Readiness"
    echo "============================================="
    echo ""

    local ready=true

    # Check credentials
    if ! check_current_credentials; then
        ready=false
    fi

    # Check if CDK is bootstrapped
    if [ -n "$DEPLOYMENT_ACCOUNT" ] && [ -n "$DEPLOYMENT_REGION" ]; then
        if check_bootstrap_needed "$DEPLOYMENT_ACCOUNT" "$DEPLOYMENT_REGION"; then
            echo "❌ CDK not bootstrapped in $DEPLOYMENT_REGION"
            echo "   Run: ./setup-and-deploy.sh bootstrap"
            ready=false
        else
            echo "✅ CDK bootstrapped in $DEPLOYMENT_REGION"
        fi
    fi

    # Check Node.js
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js not installed"
        ready=false
    else
        echo "✅ Node.js installed"
    fi

    # Check CDK app entry point
    if [ ! -f "$CDK_APP_PATH" ]; then
        echo "❌ CDK app not found: $CDK_APP_PATH"
        ready=false
    else
        echo "✅ CDK app found: $CDK_APP_PATH"
    fi

    # Check cdk.json
    if [ ! -f "cdk.json" ]; then
        echo "❌ cdk.json not found"
        ready=false
    else
        echo "✅ cdk.json found"
    fi

    # Check dependencies
    if [ ! -d "node_modules" ]; then
        echo "❌ Dependencies not installed (run: npm install)"
        ready=false
    else
        echo "✅ Dependencies installed"
    fi

    # Check ts-node
    if [ -d "node_modules" ] && [ -f "node_modules/.bin/ts-node" ]; then
        echo "✅ ts-node available"
    elif npm list ts-node &> /dev/null; then
        echo "✅ ts-node installed"
    else
        echo "⚠️  ts-node not found (will be auto-installed if needed)"
    fi

    # Check lambda packages
    if [ ! -d "lambda-packages" ] || [ ! -d "lambda-packages/handlers" ]; then
        echo "❌ Lambda packages not found"
        echo "   This package requires pre-built Lambda deployment packages."
        echo "   Please ensure lambda-packages/handlers/ directory exists with:"
        echo "     - amzn_nova_act_human_intervention/"
        echo "     - amzn_nova_act_human_intervention_common/"
        echo "     - Python dependencies"
        ready=false
    else
        # Check for required Python packages
        if [ -d "lambda-packages/handlers/amzn_nova_act_human_intervention" ] && \
           [ -d "lambda-packages/handlers/amzn_nova_act_human_intervention_common" ]; then
            echo "✅ Lambda packages present"
        else
            echo "❌ Lambda packages incomplete"
            echo "   Missing required directories in lambda-packages/handlers/"
            ready=false
        fi
    fi

    # Check build
    if [ ! -d "dist" ]; then
        echo "⚠️  Project not built (run: npm run build)"
    else
        echo "✅ Project built"
    fi

    echo ""

    if [ "$ready" = true ]; then
        echo "============================================="
        echo "✅ Ready for CDK Deployment!"
        echo "============================================="
        echo ""
        echo "CDK Configuration:"
        echo "  App: $CDK_APP_PATH"
        echo "  Stacks: 4 (Storage, Approval, UITakeover, WebSocket)"
        echo ""
        echo "Environment:"
        echo "  export DEPLOYMENT_STAGE=$DEPLOYMENT_STAGE"
        echo "  export STACK_DISAMBIGUATOR=${STACK_DISAMBIGUATOR:-$DEPLOYMENT_STAGE}"
        echo "  export DEPLOYMENT_ACCOUNT=$DEPLOYMENT_ACCOUNT"
        echo "  export DEPLOYMENT_REGION=$DEPLOYMENT_REGION"
        echo ""
        return 0
    else
        echo "❌ Not ready for deployment. Please complete the setup steps."
        return 1
    fi
}

# Full deployment workflow
full_deployment() {
    echo "============================================="
    echo "Full Deployment Workflow"
    echo "============================================="
    echo ""

    check_current_credentials || {
        echo "Please configure credentials first (option 2)"
        return 1
    }

    # Verify CDK app exists
    if ! check_cdk_app; then
        echo "❌ Cannot proceed without CDK app"
        return 1
    fi

    # Skip interactive configuration in non-interactive mode
    if [ -z "$NON_INTERACTIVE" ]; then
        configure_deployment_env
    else
        echo "Using environment configuration:"
        echo "  DEPLOYMENT_STAGE:       $DEPLOYMENT_STAGE"
        echo "  STACK_DISAMBIGUATOR:    $STACK_DISAMBIGUATOR"
        echo "  DEPLOYMENT_REGION:      $DEPLOYMENT_REGION"
        echo "  DEPLOYMENT_ACCOUNT:     $DEPLOYMENT_ACCOUNT"
        echo ""
    fi

    install_dependencies
    check_ts_node
    build_project

    # Check for failed stacks that need cleanup
    echo ""
    check_failed_stacks "$STACK_DISAMBIGUATOR" "$DEPLOYMENT_REGION" || {
        return 1
    }

    # Check if CDK is bootstrapped
    if check_bootstrap_needed "$DEPLOYMENT_ACCOUNT" "$DEPLOYMENT_REGION"; then
        echo "⚠️  CDK is not bootstrapped in $DEPLOYMENT_REGION"
        echo ""
        echo "CDK bootstrap is required for first-time deployment."
        echo "This creates necessary resources (S3 bucket, ECR repository, IAM roles, etc.)"
        echo ""
        read -p "Bootstrap CDK now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            bootstrap_cdk || {
                echo "❌ Bootstrap failed. Cannot continue with deployment."
                return 1
            }
        else
            echo "❌ Cannot deploy without bootstrapping. Exiting."
            return 1
        fi
    else
        echo "✅ CDK already bootstrapped in $DEPLOYMENT_REGION"
    fi
    echo ""

    # Check if this is first-time deployment
    if is_first_time_deployment "$STACK_DISAMBIGUATOR" "$DEPLOYMENT_REGION"; then
        echo "🆕 First-time deployment detected for disambiguator: $STACK_DISAMBIGUATOR"
        echo ""
    fi

    list_stacks
    synth_stacks
    diff_stacks

    if [ -z "$NON_INTERACTIVE" ]; then
        deploy_stacks
    else
        echo "Deploying all stacks..."
        npx cdk deploy --all --require-approval never
        echo "✅ Deployment completed!"
        show_stack_outputs
    fi
}

# Main menu
main_menu() {
    echo ""
    echo "What would you like to do?"
    echo ""
    echo "=== Setup ==="
    echo "1) 🎓 First-time AWS user setup wizard (NEW TO AWS? START HERE!)"
    echo "2) Check current credentials status"
    echo "3) Configure existing credentials (I have Access Key ID/Secret)"
    echo "4) Create new IAM user and access keys (requires admin access)"
    echo "5) Show manual setup instructions"
    echo "6) Show current environment configuration"
    echo "7) Configure deployment environment variables"
    echo ""
    echo "=== Build & Deploy ==="
    echo "8)  Prepare stacks (install + build + synth)"
    echo "9)  Install dependencies only (npm install)"
    echo "10) Build project only (npm run build)"
    echo "11) Bootstrap CDK (first time setup)"
    echo "12) List available stacks"
    echo "13) Synthesize stacks only (cdk synth)"
    echo "14) Check stack differences (cdk diff)"
    echo "15) Deploy all stacks"
    echo "16) Deploy individual stack"
    echo "17) Quick deploy (build + deploy, no prompts)"
    echo "18) Full deployment workflow (all steps)"
    echo ""
    echo "=== Manage & Monitor ==="
    echo "19) Show deployed stack outputs"
    echo "20) Show client environment variables"
    echo "21) Configure Slack bot tokens"
    echo "22) Configure SES email identities"
    echo "23) Check SES email verification status"
    echo "24) Verify CDK deployment readiness"
    echo "25) Destroy all stacks (⚠️  DANGER)"
    echo ""
    echo "26) Exit"
    echo ""
    read -r -p "Choose an option (1-26): " choice

    case $choice in
        1)
            guided_first_time_setup
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        2)
            check_current_credentials || true
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        3)
            configure_credentials_interactive
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        4)
            create_iam_user
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        5)
            show_manual_setup
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        6)
            show_env_config
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        7)
            check_current_credentials || true
            configure_deployment_env
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        8)
            prepare_stacks
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        9)
            install_dependencies
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        10)
            build_project
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        11)
            bootstrap_cdk
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        12)
            list_stacks
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        13)
            synth_stacks
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        14)
            diff_stacks
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        15)
            deploy_stacks
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        16)
            deploy_individual_stack
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        17)
            quick_deploy
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        18)
            full_deployment
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        19)
            show_stack_outputs
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        20)
            show_client_env_vars
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        21)
            configure_slack_secrets
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        22)
            configure_email_identities
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        23)
            check_email_status
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        24)
            verify_cdk_ready
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        25)
            destroy_stacks
            read -r -p "Press Enter to continue..."
            main_menu
            ;;
        26)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option. Please choose 1-26."
            main_menu
            ;;
    esac
}

# Parse command line arguments for non-interactive mode
parse_command() {
    local command="$1"
    shift  # Remove first argument, keep the rest

    # Set non-interactive flag
    export NON_INTERACTIVE=1

    case "$command" in
        # Setup commands
        first-time-setup|first-time|new-user|wizard)
            guided_first_time_setup
            ;;
        check-credentials|check)
            check_current_credentials || exit 1
            ;;
        configure|config)
            configure_credentials_interactive
            ;;
        create-user|user)
            create_iam_user
            ;;
        show-setup|setup-help)
            show_manual_setup
            ;;
        show-env|env)
            show_env_config
            ;;
        configure-env|set-env)
            configure_deployment_env
            ;;

        # Build & Deploy commands
        prepare|prep)
            prepare_stacks
            ;;
        install)
            install_dependencies
            ;;
        build)
            build_project
            ;;
        bootstrap)
            bootstrap_cdk
            ;;
        list|ls)
            list_stacks
            ;;
        synth)
            synth_stacks
            ;;
        diff)
            diff_stacks
            ;;
        deploy)
            if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
                check_current_credentials || exit 1
            fi
            echo "Deploying all stacks..."
            npx cdk deploy --all --require-approval never
            echo "✅ Deployment completed!"
            ;;
        deploy-stack)
            if [ -z "$1" ]; then
                echo "❌ Error: Stack name required"
                echo "Usage: $0 deploy-stack <stack-name>"
                echo "Example: $0 deploy-stack NovaActHITL-Storage-dev"
                exit 1
            fi
            if [ -z "$DEPLOYMENT_ACCOUNT" ] || [ -z "$DEPLOYMENT_REGION" ]; then
                check_current_credentials || exit 1
            fi
            echo "Deploying stack: $1"
            npx cdk deploy "$1" --require-approval never
            echo "✅ Stack deployed: $1"
            ;;
        quick-deploy|quick)
            quick_deploy
            ;;
        full|full-deployment)
            full_deployment
            ;;

        # Manage & Monitor commands
        outputs|output)
            show_stack_outputs
            ;;
        client-env|env-vars)
            show_client_env_vars
            ;;
        configure-slack-secrets|slack-secrets|slack)
            configure_slack_secrets
            ;;
        configure-email|email)
            configure_email_identities
            ;;
        check-email-status|email-status)
            check_email_status
            ;;
        verify|check-ready)
            verify_cdk_ready
            ;;
        destroy)
            destroy_stacks
            ;;

        # Help
        help|--help|-h)
            show_usage
            ;;

        # Interactive mode flag (should not reach here normally, but handle it)
        -i|--interactive)
            echo "⚠️  Interactive flag should be used without other commands"
            echo "   Usage: $0 -i"
            echo ""
            # Unset non-interactive and fall through to menu
            unset NON_INTERACTIVE
            return 0
            ;;

        # Unknown command
        *)
            echo "❌ Unknown command: $command"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Start the script
check_aws_cli
check_nodejs

# Verify CDK app exists
if ! check_cdk_app; then
    echo "❌ CDK application entry point not found!"
    echo "   Please ensure you're running this script from the project root."
    echo "   Expected file: $CDK_APP_PATH"
    exit 1
fi

# Determine mode based on arguments
if [ $# -eq 0 ]; then
    # No arguments - default to check-credentials
    parse_command "check-credentials"
    exit 0
elif [[ "$1" == "-i" ]] || [[ "$1" == "--interactive" ]]; then
    # Interactive mode flag - show menu
    # Check if credentials already exist and are correct
    if check_current_credentials; then
        if verify_cdk_ready; then
            echo ""
            read -p "Setup looks good! Proceed to full deployment? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                full_deployment
                exit 0
            fi
        fi
    fi

    # Show menu if not ready
    main_menu
else
    # Non-interactive mode - execute command and exit
    parse_command "$@"
    exit 0
fi
