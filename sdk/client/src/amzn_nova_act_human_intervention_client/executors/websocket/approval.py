"""Approval intervention executor."""

import json
import uuid
from datetime import datetime, timezone

import boto3  # type: ignore[import-untyped]
from amzn_nova_act_human_intervention_common import (
    ApprovalRequest,
    ApprovalStepFunctionInput,
    ExecutionStatus,
    ExecutorRequest,
    GenericDict,
    InterventionContext,
    UseCase,
    Utils,
)
from websocket import WebSocket

from amzn_nova_act_human_intervention_client.credentials import CredentialsProvider
from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors.websocket.executor import (
    WebsocketBasedInterventionExecutor,
)
from amzn_nova_act_human_intervention_client.utils.constants import (
    DEFAULT_EXECUTION_TIMEOUT,
    S3_PRESIGNED_URL_EXPIRATION,
    S3_SCREENSHOT_OBJECT_KEY_TEMPLATE,
)


class ApprovalInterventionExecutor(WebsocketBasedInterventionExecutor[ApprovalRequest]):
    """WebSocket-based intervention executor for approval interventions.

    Handles requests for human approval or decision-making in automated processes.
    Requires S3 bucket for screenshot storage.

    This executor:
        - Uploads screenshots to S3 with presigned URLs
        - Sends approval requests to human reviewers
        - Waits for approval decision (approve/reject/terminate)
        - Returns the decision to the caller

    Examples
    --------
    Basic approval workflow with default options:

    >>> from amzn_nova_act_human_intervention_client import (
    ...     ApprovalInterventionExecutor,
    ...     AssumedRoleCredentialsProvider
    ... )
    >>> from amzn_nova_act_human_intervention_common import (
    ...     ApprovalRequest,
    ...     InterventionContext,
    ...     EmailContactInfo
    ... )
    >>>
    >>> # Set up credentials
    >>> credentials = AssumedRoleCredentialsProvider(
    ...     role_arn="arn:aws:iam::123456789012:role/MyRole",
    ...     duration_seconds=3600
    ... )
    >>>
    >>> # Create intervention context
    >>> context = InterventionContext(
    ...     workflow_run_id="run-123",
    ...     act_session_id="session-456",
    ...     act_id="act-789"
    ... )
    >>>
    >>> # Create executor
    >>> executor = ApprovalInterventionExecutor(
    ...     endpoint="wss://myapi.execute-api.us-west-2.amazonaws.com/prod",
    ...     intervention_context=context,
    ...     screenshot_s3_bucket="my-screenshots-bucket",
    ...     credentials_provider=credentials,
    ...     region="us-west-2"
    ... )
    >>>
    >>> # Create approval request with notification
    >>> approval = ApprovalRequest(
    ...     question="Should we proceed with this action?",
    ...     most_recent_screenshot="data:image/png;base64,iVBORw0KG...",
    ...     notification_recipients=[
    ...         EmailContactInfo(email="reviewer@example.com")
    ...     ]
    ... )
    >>>
    >>> # Execute and wait for human decision
    >>> executor.run(approval)
    >>> print(executor.completion_response)
    {'type': 'workflow_completed', 'executionStatus': 'SUCCEEDED', 'approvalAction': 'APPROVED'}

    Custom approval with multiple options and longer timeout:

    >>> from amzn_nova_act_human_intervention_common import ApprovalOption
    >>>
    >>> # Create custom approval options
    >>> approval = ApprovalRequest(
    ...     question="Which deployment strategy should we use?",
    ...     most_recent_screenshot="data:image/png;base64,iVBORw0KG...",
    ...     options=[
    ...         ApprovalOption(label="Blue/Green", value="blue_green"),
    ...         ApprovalOption(label="Canary", value="canary"),
    ...         ApprovalOption(label="Rolling", value="rolling")
    ...     ],
    ...     notification_recipients=[
    ...         EmailContactInfo(email="devops@example.com")
    ...     ]
    ... )
    >>>
    >>> # Create executor with 2-hour timeout
    >>> executor = ApprovalInterventionExecutor(
    ...     endpoint="wss://myapi.execute-api.us-west-2.amazonaws.com/prod",
    ...     intervention_context=context,
    ...     screenshot_s3_bucket="my-screenshots-bucket",
    ...     credentials_provider=credentials,
    ...     execution_timeout=7200  # 2 hours
    ... )
    >>>
    >>> executor.run(approval)

    Handling approval errors:

    >>> from amzn_nova_act_human_intervention_client import WorkflowExecutionError
    >>>
    >>> try:
    ...     executor.run(approval)
    ...     print(f"Decision: {executor.completion_response['approvalAction']}")
    ... except WorkflowExecutionError as e:
    ...     print(f"Workflow was terminated: {e.message}")
    ... except RuntimeError as e:
    ...     print(f"Workflow failed: {e}")
    """

    def __init__(
        self,
        endpoint: str,
        intervention_context: InterventionContext,
        screenshot_s3_bucket: str,
        credentials_provider: CredentialsProvider,
        region: str = "us-west-2",
        execution_timeout: int = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        """Initialize the Approval intervention executor.

        Args:
            endpoint: WebSocket endpoint URL
            intervention_context: Context information for the intervention
            screenshot_s3_bucket: S3 bucket name for storing screenshots (required for Approval)
            credentials_provider: Provider for AWS credentials (handles refresh)
            region: AWS region for SigV4 signing
            execution_timeout: URL expiration time in seconds (default: 1 hour, max: 24 hours)

        Raises:
            ValueError: If screenshot_s3_bucket is not provided
        """
        if not screenshot_s3_bucket:
            raise ValueError("screenshot_s3_bucket is required for ApprovalInterventionExecutor")

        super().__init__(
            endpoint=endpoint,
            intervention_context=intervention_context,
            credentials_provider=credentials_provider,
            region=region,
            execution_timeout=execution_timeout,
        )

        # S3 configuration for screenshot storage
        self.screenshot_s3_bucket = screenshot_s3_bucket

        # Create S3 client with assumed role credentials
        # Ensure credentials are valid via provider
        credentials = self._credentials_provider.credentials

        # Create S3 client using the credentials from the provider
        self._s3_client = boto3.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.token,
        )
        self.logger.info("S3 client created with current credentials")

    def _create_message(self, input_data: ApprovalRequest) -> GenericDict:
        """Create approval message.

        Args:
            input_data: Approval request data

        Returns:
            WebSocket message for approval request
        """
        # Generate event ID for this message
        event_id: str = str(uuid.uuid4())

        # Upload original screenshot to S3
        screenshot_url = self._upload_screenshot_to_s3(input_data.most_recent_screenshot, event_id)
        self.logger.info(f"Screenshot uploaded to S3, presigned URL: {screenshot_url[:100]}...")

        approval_input = ApprovalStepFunctionInput(
            timeout=self._execution_timeout,
            workflow_run_id=self._intervention_context.workflow_run_id,
            session_id=self._intervention_context.act_session_id,
            act_id=self._intervention_context.act_id,
            most_recent_screenshot=screenshot_url,
            event_id=event_id,
            type=UseCase.APPROVAL,
            query=input_data.question,
            options=input_data.options,  # ApprovalRequest has default ApprovalOption objects
            notification_recipients=input_data.notification_recipients,
        )

        message = ExecutorRequest(action=self._execution_action_name, input=approval_input)
        return message.model_dump(mode="json")

    def _upload_screenshot_to_s3(self, data_url: str, event_id: str) -> str:
        """Upload screenshot data URL to S3 as text and return presigned URL.

        Stores the complete data URL (including header) as a text file in S3.
        The backend will download this text and use it directly in the HTML.

        Args:
            data_url: Base64 encoded data URL of the screenshot (e.g., "data:image/png;base64,...")
            event_id: Event ID for the screenshot

        Returns:
            Presigned S3 URL for accessing the screenshot data URL

        Raises:
            ValueError: If data URL format is invalid
        """
        if not data_url.startswith("data:"):
            raise ValueError("Invalid data URL format - must start with 'data:'")

        # Generate S3 object key using template (use .txt extension for text content)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        object_key = S3_SCREENSHOT_OBJECT_KEY_TEMPLATE.format(
            event_id=event_id,
            timestamp=timestamp,
            extension=".txt",  # Store as text file
        )

        # Upload data URL as text to S3
        self.logger.info(f"Uploading screenshot data URL to s3://{self.screenshot_s3_bucket}/{object_key}")
        self._s3_client.put_object(
            Bucket=self.screenshot_s3_bucket,
            Key=object_key,
            Body=data_url.encode("utf-8"),  # Store complete data URL as UTF-8 text
            ContentType="text/plain",
            ServerSideEncryption="aws:kms",  # Use KMS encryption (bucket's default key)
        )

        # Generate presigned URL with expiration matching execution timeout
        presigned_url_expiration = min(self._execution_timeout, S3_PRESIGNED_URL_EXPIRATION)
        presigned_url = self._s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.screenshot_s3_bucket, "Key": object_key},
            ExpiresIn=presigned_url_expiration,
        )

        self.logger.info(f"Screenshot uploaded, presigned URL expires in {presigned_url_expiration} seconds")
        return presigned_url

    def _on_message(self, app: WebSocket, message: str) -> None:
        """Handle incoming WebSocket messages for approval workflow.

        Args:
            app: WebSocket connection
            message: Raw message string received from server
        """
        if Utils.is_valid_json(message):
            rcvd_message: GenericDict = json.loads(message)
            message_type = rcvd_message.get("type")

            if message_type == "workflow_started":
                self.logger.info(f"[Approval Workflow Started] Event ID: {rcvd_message.get('eventId')}")
                self.logger.info(f"  Workflow Run ID: {rcvd_message.get('workflowRunId')}")
                self.logger.info(f"  Session ID: {rcvd_message.get('sessionId')}")
                self.logger.info(f"  SPA URL: {rcvd_message.get('spaUrl')}")
                self.logger.info(f"  Message: {rcvd_message.get('message')}")

                self._is_reconnecting = False  # Reset reconnection flag on successful message

            elif message_type == "workflow_completed":
                execution_status = rcvd_message.get("executionStatus")
                approval_action = rcvd_message.get("approvalAction")

                self.logger.info(f"[Approval Workflow Completed] Event ID: {rcvd_message.get('eventId')}")
                self.logger.info(f"  Execution Status: {execution_status}")
                self.logger.info(f"  Approval Action: {approval_action}")
                self.logger.info(f"  Message: {rcvd_message.get('message')}")

                self._completion_received = True
                self.completion_response = rcvd_message
                self._handle_completion(app, rcvd_message)

                # Store exception for failed workflows to re-raise after event loop
                # WorkflowExecutionError only for TERMINATED status
                # RuntimeError for FAILED or null/missing executionStatus
                if execution_status is None:
                    error_msg = "Approval workflow completed with null executionStatus"
                    self.logger.error(error_msg)
                    self._exception = RuntimeError(error_msg)
                elif execution_status == ExecutionStatus.TERMINATED.value:
                    additional_message = rcvd_message.get("message")
                    self.logger.error(f"Approval workflow terminated: {execution_status}")
                    self._exception = WorkflowExecutionError(
                        status=ExecutionStatus.TERMINATED,
                        workflow_type="Approval",
                        message=additional_message,
                    )
                elif execution_status == ExecutionStatus.FAILED.value:
                    error_msg = f"Approval workflow failed with status: {execution_status}"
                    additional_message = rcvd_message.get("message")
                    if additional_message:
                        error_msg = f"{error_msg} - {additional_message}"
                    self.logger.error(error_msg)
                    self._exception = RuntimeError(error_msg)

            else:
                self.logger.info(f"Approval message received: {rcvd_message}")
