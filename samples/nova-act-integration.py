"""Human Input Callbacks implementation for Nova Act using HITL Client.

This module provides an implementation of HumanInputCallbacksBase that integrates
with the Nova Act Human Intervention service to handle human-in-the-loop scenarios
during Nova Act execution.

The implementation supports two use cases:
1. Approval: Request human approval for specific actions (e.g., financial transactions)
2. UI Takeover: Request human intervention for complex UI interactions (e.g., CAPTCHAs)

Example usage:
    # Local development with AWS profile:
    AWS_PROFILE=your-profile python nova-act-integration.py \
        --aws-region us-east-1 \
        --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
        --execution-timeout 7200 \
        --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
        --screenshot-s3-bucket your-screenshot-bucket \
        --use-case Approval

    # AWS deployment (ECS/Lambda/EC2) with IAM role:
    python nova-act-integration.py \
        --aws-region us-east-1 \
        --executor-endpoint wss://your-api-id.execute-api.us-east-1.amazonaws.com/prod \
        --execution-timeout 7200 \
        --executor-iam-role-arn arn:aws:iam::123456789012:role/YourExecutionRole \
        --screenshot-s3-bucket your-screenshot-bucket \
        --use-case UITakeover
"""

import logging
import os

import boto3
import click
from amzn_nova_act_human_intervention_client import (
    ApprovalInterventionExecutor,
    ApprovalRequest,
    AssumedRoleCredentialsProvider,
    BrowserSessionContext,
    UITakeoverInterventionExecutor,
    UITakeoverRequest,
    WorkflowExecutionError,
)
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    EmailContactInfo,
    InterventionContext,
    NotificationRecipient,
    UseCase,
)
from bedrock_agentcore.tools.browser_client import browser_session
from nova_act.nova_act import HumanInputCallbacksBase, NovaAct, Workflow
from nova_act.tools.human.interface.human_input_callback import ApprovalResponse, UiTakeoverResponse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Test prompts for different use cases
APPROVAL_PROMPT = """
Click on book your journey.
Find flights from Boston to Wolf on Feb 22nd
In the top most search result, if the Economy
option price > 100, please request for approval.
If approved, please click on select and close
the page and mark the task as success, else
just fail.
"""
APPROVAL_URL = "https://nova.amazon.com/act/gym"

UI_TAKEOVER_PROMPT = """Attempt to submit the form. Return if you see 'Verification Success... Hooray!'."""
UI_TAKEOVER_URL = "https://www.google.com/recaptcha/api2/demo"


class NovaActHumanInputCallbacks(HumanInputCallbacksBase):
    """Implementation of HumanInputCallbacksBase for Nova Act integration.

    This class provides concrete implementations of the approve() and ui_takeover()
    methods by delegating to the appropriate HITL intervention executors.

    Attributes:
        _browser_session_id: Optional browser session ID for UI takeover operations
        _credentials_provider: AWS credentials provider for intervention executors
    """

    def __init__(
        self,
        workflow_run_id: str,
        aws_region: str,
        executor_endpoint: str,
        execution_timeout: int,
        executor_iam_role_arn: str,
        screenshot_s3_bucket: str,
        browser_session_id: str | None = None,
        credentials_provider: AssumedRoleCredentialsProvider | None = None,
        boto_session: boto3.Session | None = None,
    ) -> None:
        """Initialize the Nova Act Human Input Callbacks provider.

        Args:
            workflow_run_id: Workflow run ID for tracking interventions
            aws_region: AWS region
            executor_endpoint: HITL executor endpoint
            execution_timeout: Execution timeout in seconds
            executor_iam_role_arn: IAM role ARN for executor
            screenshot_s3_bucket: S3 bucket for screenshots
            browser_session_id: Optional browser session ID from Nova Act for UI takeover.
            credentials_provider: Optional credentials provider.
            boto_session: Optional boto3 session.
        """
        super().__init__()
        self._workflow_run_id = workflow_run_id
        self._browser_session_id = browser_session_id
        self._aws_region = aws_region
        self._executor_endpoint = executor_endpoint
        self._execution_timeout = execution_timeout
        self._executor_iam_role_arn = executor_iam_role_arn
        self._screenshot_s3_bucket = screenshot_s3_bucket

        self._credentials_provider = credentials_provider or AssumedRoleCredentialsProvider(
            role_arn=executor_iam_role_arn, duration_seconds=execution_timeout, session=boto_session
        )
        logger.info("Initialized NovaActHumanInputCallbacks")

    def set_browser_session_id(self, browser_session_id: str) -> None:
        """Set the browser session ID for UI takeover operations.

        Args:
            browser_session_id: The browser session ID from Nova Act
        """
        self._browser_session_id = browser_session_id
        logger.info(f"Set browser session ID: {browser_session_id}")

    def _create_intervention_context(self) -> InterventionContext:
        """Create an intervention context using Act session ID and Act ID.

        Returns:
            InterventionContext with workflow run ID, session ID, and act ID
        """
        # Generate a unique workflow run ID for this intervention

        return InterventionContext(
            workflow_run_id=self._workflow_run_id,
            act_session_id=self.act_session_id,
            act_id=self.current_act_id,
        )

    def approve(self, message: str) -> ApprovalResponse:
        """Request human approval for a specific action.

        This method creates an approval intervention workflow that:
        1. Captures a screenshot of the current browser state
        2. Uploads the screenshot to S3
        3. Sends an approval request via WebSocket
        4. Waits for the user's response (Approve/Deny)
        5. Returns the approval decision

        Args:
            message: Clear description of what requires approval

        Returns:
            bool: True if approved, False if denied

        Raises:
            RuntimeError: If the intervention workflow fails
            TimeoutError: If the user doesn't respond within the timeout period
        """
        logger.info(f"Approval requested: {message}")

        try:
            # Create intervention context
            context = self._create_intervention_context()

            # Initialize approval executor
            executor = ApprovalInterventionExecutor(
                endpoint=self._executor_endpoint,
                intervention_context=context,
                screenshot_s3_bucket=self._screenshot_s3_bucket,
                credentials_provider=self._credentials_provider,
                region=self._aws_region,
                execution_timeout=self._execution_timeout,
            )

            logger.info(f"Starting approval intervention workflow (ID: {context.workflow_run_id})...")

            # Execute approval workflow
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
                                from_email_address="noreply@example.com",
                            )
                        ),
                    ],
                    most_recent_screenshot=self.most_recent_screenshot,
                )
            )

            # Check the response
            response = executor.completion_response
            if response is None:
                raise RuntimeError("No response received from approval workflow")

            approved: bool = response.get("approvalAction") == ApprovalAction.APPROVE.value
            logger.info(f"Approval workflow completed. Approved: {approved}")
            if approved:
                return ApprovalResponse.YES
            # Request was denied.
            # Here HITL workflow was successful but should return CANCEL
            return ApprovalResponse.CANCEL

        except WorkflowExecutionError as e:
            # User-initiated termination - return CANCEL
            logger.error(f"Approval workflow terminated by user: {e}", exc_info=True)
            return ApprovalResponse.CANCEL
        except Exception as e:
            # Other errors (FAILED status, connection issues, etc.) - re-raise
            logger.error(f"Approval workflow failed: {e}", exc_info=True)
            raise e

    def ui_takeover(self, message: str) -> UiTakeoverResponse:
        """Request human takeover for UI interactions.

        This method creates a UI takeover intervention workflow that:
        1. Sends a UI takeover request with browser session ID
        2. Generates an SPA with embedded browser interface
        3. Notifies the user to take over
        4. Waits for the user to complete the task
        5. Returns control to the automation

        Args:
            message: Clear description of what human input is needed

        Raises:
            RuntimeError: If browser session ID is not set or workflow fails
            TimeoutError: If the user doesn't complete the task within the timeout period
        """
        logger.info(f"UI Takeover requested: {message}")

        if not self._browser_session_id:
            logger.error("Browser session ID not set. Call set_browser_session_id() before requesting UI takeover.")
            return UiTakeoverResponse.CANCEL

        try:
            # Create intervention context
            context = self._create_intervention_context()

            # Initialize UI takeover executor
            executor = UITakeoverInterventionExecutor(
                endpoint=self._executor_endpoint,
                intervention_context=context,
                credentials_provider=self._credentials_provider,
                region=self._aws_region,
                execution_timeout=self._execution_timeout,
            )

            logger.info(f"Starting UI takeover intervention workflow (ID: {context.workflow_run_id})...")

            # Execute UI takeover workflow
            executor.run(
                UITakeoverRequest(
                    message=message,
                    browser_session=BrowserSessionContext(session_id=self._browser_session_id),
                    notification_recipients=[
                        NotificationRecipient(
                            contact_info=EmailContactInfo(
                                to_email_address="user@example.com", from_email_address="noreply@example.com"
                            )
                        )
                    ],
                )
            )

            logger.info("UI takeover workflow completed")
            return UiTakeoverResponse.COMPLETE

        except WorkflowExecutionError as e:
            # User-initiated termination - return CANCEL
            logger.error(f"UI takeover workflow terminated by user: {e}", exc_info=True)
            return UiTakeoverResponse.CANCEL
        except Exception as e:
            # Other errors (FAILED status, connection issues, etc.) - re-raise
            logger.error(f"UI takeover workflow failed: {e}", exc_info=True)
            raise e


# Example usage for testing
def main(
    use_case: UseCase,
    aws_region: str,
    executor_endpoint: str,
    execution_timeout: int,
    executor_iam_role_arn: str,
    screenshot_s3_bucket: str,
):
    """Example usage of NovaActHumanInputCallbacks.

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
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        logger.info(f"Using AWS profile from AWS_PROFILE: {profile}")
    else:
        logger.info("Using default AWS credential chain (IAM role)")

    workflow_boto_session_args = {"region_name": aws_region}
    prompt, starting_url = (
        (APPROVAL_PROMPT, APPROVAL_URL) if use_case == UseCase.APPROVAL else (UI_TAKEOVER_PROMPT, UI_TAKEOVER_URL)
    )
    with browser_session(aws_region) as agent_core_browser:
        ws_url, headers = agent_core_browser.generate_ws_headers()
        with Workflow(
            boto_session_kwargs=workflow_boto_session_args,
            model_id="nova-act-latest",
            workflow_definition_name="nova-act-hitl-example",
        ) as workflow:
            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                starting_page=starting_url,
                tty=False,
                human_input_callbacks=NovaActHumanInputCallbacks(
                    workflow_run_id=workflow.workflow_run_id,
                    aws_region=aws_region,
                    executor_endpoint=executor_endpoint,
                    execution_timeout=execution_timeout,
                    executor_iam_role_arn=executor_iam_role_arn,
                    screenshot_s3_bucket=screenshot_s3_bucket,
                    browser_session_id=agent_core_browser.session_id,
                    boto_session=boto3.Session(**workflow_boto_session_args),
                ),
                workflow=workflow,
            ) as nova:
                result = nova.act_get(prompt=prompt)
                print(f"Task completed: {result}")


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
    """NovaAct Human-in-the-Loop Integration Example

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
