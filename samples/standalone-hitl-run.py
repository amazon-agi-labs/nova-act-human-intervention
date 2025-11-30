"""Example usage of the Nova Act Human Intervention Client.

This module demonstrates how to use the WebSocket-based intervention executors
for both Approval and UI Takeover use cases.

Requirements:
    - AWS credentials configured (via environment variables, ~/.aws/credentials, or IAM role)
    - IAM role with permissions:
        * execute-api:ManageConnections and execute-api:Invoke for WebSocket API
        * s3:PutObject for screenshot S3 bucket (Approval use case only)
    - Valid WebSocket endpoint URL
    - Screenshot image file for Approval use case

Credentials Provider Pattern:
    - Create an AssumedRoleCredentialsProvider with the IAM role ARN
    - Pass the credentials provider to the executor
    - The provider handles role assumption and credential refresh
    - The executor uses credentials from the provider for ALL AWS operations:
        * WebSocket SigV4 signing
        * S3 screenshot uploads
    - The executor schedules credential refresh before expiration

Example usage:
    # Local development with AWS profile:
    AWS_PROFILE=your-profile python standalone-hitl-run.py \
        --aws-region us-east-1 \
        --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
        --execution-timeout 7200 \
        --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
        --screenshot-s3-bucket your-screenshot-bucket \
        --use-case Approval

    # AWS deployment (ECS/Lambda/EC2) with IAM role:
    python standalone-hitl-run.py \
        --aws-region us-east-1 \
        --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
        --execution-timeout 28800 \
        --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
        --screenshot-s3-bucket your-screenshot-bucket \
        --use-case UI_TAKEOVER
"""

import base64
import os
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import boto3
import click
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    ApprovalRequest,
    AssumedRoleCredentialsProvider,
    BrowserSessionContext,
    UITakeoverInterventionExecutor,
    UITakeoverRequest,
)
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
    UseCase,
)
from bedrock_agentcore.tools import browser_session
from botocore.exceptions import ClientError
from PIL import Image  # type: ignore[import-untyped]


@contextmanager
def browser_session_with_cleanup(region: str, **kwargs):
    """Context manager that wraps browser_session and handles ConflictException on cleanup.

    When a UI Takeover workflow completes, the browser session may be stopped by the backend
    or user before the context manager exits. This wrapper gracefully handles the
    ConflictException that occurs when trying to stop an already-stopped session.

    The browser_session context manager automatically calls stop() on exit. If the session
    was already stopped (e.g., by the backend or user during the workflow), this will raise
    a ConflictException which we catch and suppress.

    Args:
        region: AWS region for the browser session
        **kwargs: Additional arguments to pass to browser_session

    Yields:
        BrowserClient: The browser session client
    """
    try:
        with browser_session(region=region, **kwargs) as session:
            yield session
    except ClientError as e:
        # Handle botocore.errorfactory.ConflictException (a subclass of ClientError)
        # This occurs when browser_session's __exit__ tries to stop an already-stopped session
        if e.response["Error"]["Code"] == "ConflictException" or e.__class__.__name__ == "ConflictException":
            # Session already stopped - this is expected behavior
            pass
        else:
            raise


def load_screenshot_as_data_url(image_path: str) -> str:
    """Load an image file and convert it to a Base64 encoded data URL.

    The data URL format (e.g., "data:image/jpeg;base64,...") is used for efficient
    storage and transmission. The complete data URL is uploaded to S3 as a text file,
    then the backend downloads it and embeds it directly in the HTML SPA.

    Args:
        image_path: Path to the image file (JPEG, PNG, GIF, or WEBP)

    Returns:
        Base64 encoded data URL string (e.g., "data:image/jpeg;base64,...")

    Raises:
        FileNotFoundError: If the image file doesn't exist
        PIL.UnidentifiedImageError: If the file is not a valid image
    """
    # Open and validate image using PIL
    image = Image.open(image_path)

    # Determine MIME type from image format
    format_to_mime = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    mime_type = format_to_mime.get(image.format, "image/jpeg")

    # Convert image to bytes
    buffer = BytesIO()
    image.save(buffer, format=image.format or "JPEG")
    image_bytes = buffer.getvalue()

    # Encode to Base64 and create data URL
    base64_encoded = base64.b64encode(image_bytes).decode("utf-8")

    return f"data:{mime_type};base64,{base64_encoded}"


def approval_example(
    screenshot_data_url: str,
    boto_session: boto3.Session,
    aws_region: str,
    executor_endpoint: str,
    execution_timeout: int,
    executor_iam_role_arn: str,
    screenshot_s3_bucket: str,
):
    """Execute an Approval intervention workflow.

    This example demonstrates how to:
    1. Create an InterventionContext with workflow identifiers
    2. Initialize an ApprovalInterventionExecutor with required parameters
    3. Load and convert a screenshot to a data URL
    4. Send an approval request with the screenshot
    5. Wait for the user's response

    The workflow:
    1. Client uploads screenshot data URL to S3 as text
    2. Client connects to WebSocket API using SigV4 signed URL
    3. Client sends approval request with S3 presigned URL for screenshot
    4. Backend downloads screenshot data URL from S3
    5. Backend generates SPA with embedded screenshot
    6. Backend deletes screenshot from S3 (lifecycle policy deletes after 1 day as backup)
    7. User receives notification and opens SPA
    8. User selects an option (Approve/Deny)
    9. Client receives workflow completion message via WebSocket

    Args:
        screenshot_data_url: Base64-encoded data URL of the screenshot
        boto_session: boto3 session for AWS operations
    """
    # Create intervention context with unique identifiers
    # These IDs should come from your ACT workflow orchestration system
    context = InterventionContext(
        workflow_run_id="550e8400-e29b-41d4-a716-446655440000",
        act_session_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        act_id="6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    )

    # Create credentials provider for IAM role assumption
    # The provider handles:
    # - Automatic role assumption via STS
    # - Credential refresh before expiration
    # - Credential storage and retrieval
    credentials_provider = AssumedRoleCredentialsProvider(
        role_arn=executor_iam_role_arn, duration_seconds=execution_timeout, session=boto_session
    )

    # Initialize the Approval executor
    # The executor handles:
    # - WebSocket connection with SigV4 signing using provided credentials
    # - S3 client creation with credentials from provider
    # - Screenshot upload to S3 using the credentials
    # - Message sending and receiving
    # - Connection lifecycle (keep-alive, reconnection, expiry)
    # - Scheduled credential refresh coordination
    executor = ApprovalInterventionExecutor(
        endpoint=executor_endpoint,
        intervention_context=context,
        screenshot_s3_bucket=screenshot_s3_bucket,
        credentials_provider=credentials_provider,
        region=aws_region,
        execution_timeout=execution_timeout,
    )

    print("Starting Approval intervention workflow...")
    print(f"  Workflow Run ID: {context.workflow_run_id}")
    print(f"  Screenshot size: {len(screenshot_data_url)} characters")

    # Execute the intervention workflow
    # This blocks until the workflow completes or times out
    executor.run(
        ApprovalRequest(
            question="Are you sure you want to proceed with this operation?",
            options=[
                ApprovalOption(label="Approve Request", action=ApprovalAction.APPROVE),
                ApprovalOption(label="Deny", action=ApprovalAction.DENY),
            ],
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com",
                        from_email_address="noreply@example.com",
                    )
                ),
            ],
            most_recent_screenshot=screenshot_data_url,
        )
    )

    print("\nIntervention completed!")
    print(f"Response: {executor.completion_response}")


def ui_takeover_example(
    boto_session: boto3.Session,
    aws_region: str,
    executor_endpoint: str,
    execution_timeout: int,
    executor_iam_role_arn: str,
):
    """Execute a UI Takeover intervention workflow.

    This example demonstrates how to:
    1. Create an InterventionContext with workflow identifiers
    2. Initialize a UITakeoverInterventionExecutor
    3. Send a UI takeover request with browser session context
    4. Wait for the user to complete the task

    The workflow:
    1. Client connects to WebSocket API using SigV4 signed URL
    2. Client sends UI takeover request with browser session ID
    3. Backend generates SPA with embedded browser interface
    4. User receives notification and opens SPA
    5. User takes over the browser session and completes the task
    6. User submits completion
    7. Client receives workflow completion message via WebSocket

    Note: UI Takeover does NOT require screenshot upload or S3 permissions.

    Args:
        boto_session: boto3 session for AWS operations
    """
    # Create intervention context with unique identifiers
    context = InterventionContext(
        workflow_run_id="550e8400-e29b-41d4-a716-446655440000",
        act_session_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        act_id="6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    )

    # Create credentials provider for IAM role assumption
    # The provider handles:
    # - Automatic role assumption via STS
    # - Credential refresh before expiration
    # - Credential storage and retrieval
    credentials_provider = AssumedRoleCredentialsProvider(
        role_arn=executor_iam_role_arn, duration_seconds=execution_timeout, session=boto_session
    )

    # Initialize the UI Takeover executor
    # The executor handles:
    # - WebSocket connection with SigV4 signing using provided credentials
    # - Message sending and receiving
    # - Connection lifecycle (keep-alive, reconnection, expiry)
    # - Scheduled credential refresh coordination
    executor = UITakeoverInterventionExecutor(
        endpoint=executor_endpoint,
        intervention_context=context,
        credentials_provider=credentials_provider,
        region=aws_region,
        execution_timeout=execution_timeout,
    )

    print("Starting UI Takeover intervention workflow...")
    print(f"  Workflow Run ID: {context.workflow_run_id}")

    # Execute the intervention workflow
    # This blocks until the workflow completes or times out
    with browser_session_with_cleanup(region=aws_region) as agent_core_browser:
        executor.run(
            UITakeoverRequest(
                message="Please complete the checkout process for order #12345",
                browser_session=BrowserSessionContext(session_id=agent_core_browser.session_id),
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="user@example.com",
                            from_email_address="noreply@example.com",
                        )
                    ),
                ],
            )
        )

    print("\nIntervention completed!")
    print(f"Response: {executor.completion_response}")


def main(
    use_case: UseCase,
    aws_region: str,
    executor_endpoint: str,
    execution_timeout: int,
    executor_iam_role_arn: str,
    screenshot_s3_bucket: str,
):
    """Run example workflows.

    Args:
        use_case: The use case to demonstrate (APPROVAL or UI_TAKEOVER)
        aws_region: AWS region
        executor_endpoint: HITL executor endpoint
        execution_timeout: Execution timeout in seconds
        executor_iam_role_arn: IAM role ARN for executor
        screenshot_s3_bucket: S3 bucket for screenshots

    Note:
        Set AWS_PROFILE environment variable to use a specific AWS profile.
        On AWS deployments (ECS/Lambda/EC2), IAM role credentials are used automatically.
    """
    # Create boto3 session - uses AWS_PROFILE env var if set, otherwise default credentials
    boto_session = boto3.Session(region_name=aws_region)

    profile = os.environ.get("AWS_PROFILE")
    if profile:
        print(f"Using AWS profile from AWS_PROFILE: {profile}\n")
    else:
        print("Using default AWS credential chain (IAM role)\n")

    print("=" * 80)
    print("Nova Act Human Intervention Client - Example Usage")
    print("=" * 80)
    print()

    if use_case == UseCase.APPROVAL:
        # Run Approval example (requires screenshot file and S3 permissions)
        print("Running Approval example...")
        print("-" * 80)
        # Load screenshot and convert to Base64 data URL
        # The screenshot shows the current state requiring approval
        screenshot_path = Path(__file__).parent / "test_screenshot.png"
        screenshot_data_url = load_screenshot_as_data_url(str(screenshot_path))
        approval_example(
            screenshot_data_url,
            boto_session,
            aws_region,
            executor_endpoint,
            execution_timeout,
            executor_iam_role_arn,
            screenshot_s3_bucket,
        )
        print()
    elif use_case == UseCase.UI_TAKEOVER:
        # Run UI Takeover example (no screenshot required)
        print("Running UI Takeover example...")
        print("-" * 80)
        ui_takeover_example(
            boto_session,
            aws_region,
            executor_endpoint,
            execution_timeout,
            executor_iam_role_arn,
        )
        print()


@click.command()
@click.option("--aws-region", default=lambda: os.environ["AWS_REGION"], help="AWS region")
@click.option(
    "--executor-endpoint",
    default=lambda: os.environ["HITL_EXECUTOR_ENDPOINT"],
    help="HITL executor endpoint",
)
@click.option(
    "--execution-timeout",
    type=int,
    default=lambda: int(os.environ["HITL_EXECUTION_TIMEOUT"]),
    help="Execution timeout in seconds",
)
@click.option(
    "--executor-iam-role-arn",
    default=lambda: os.environ["HITL_IAM_ROLE_ARN"],
    help="IAM role ARN for executor",
)
@click.option(
    "--screenshot-s3-bucket",
    default=lambda: os.environ["HITL_SCREENSHOT_S3_BUCKET"],
    help="S3 bucket for screenshots",
)
@click.option(
    "--use-case", type=click.Choice([e.value for e in UseCase]), required=True, help="Use case to demonstrate"
)
def cli(aws_region, executor_endpoint, execution_timeout, executor_iam_role_arn, screenshot_s3_bucket, use_case):
    """NovaAct Human Intervention Client - Standalone Example

    Use AWS_PROFILE environment variable to specify AWS profile for local development.
    """
    use_case_enum = UseCase(use_case)
    main(
        use_case_enum,
        aws_region,
        executor_endpoint,
        execution_timeout,
        executor_iam_role_arn,
        screenshot_s3_bucket,
    )


if __name__ == "__main__":
    cli()
