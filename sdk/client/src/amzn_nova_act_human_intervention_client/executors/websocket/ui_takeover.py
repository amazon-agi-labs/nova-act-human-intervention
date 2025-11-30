"""UI Takeover intervention executor."""

import json
import uuid
from typing import Any, Dict

from amzn_nova_act_human_intervention_common import (
    BrowserSessionContext,
    ExecutionStatus,
    ExecutorRequest,
    GenericDict,
    UITakeoverRequest,
    UITakeoverStepFunctionInput,
    UseCase,
    Utils,
)
from websocket import WebSocket

from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors.websocket.executor import (
    WebsocketBasedInterventionExecutor,
)


class UITakeoverInterventionExecutor(WebsocketBasedInterventionExecutor[UITakeoverRequest]):
    """WebSocket-based intervention executor for UI takeover interventions.

    Handles requests for human intervention in browser-based tasks,
    such as solving CAPTCHAs or handling complex UI interactions.

    This executor:
        - Connects to an active browser session
        - Allows human to take control of the browser
        - Waits for human to complete the task
        - Returns control to the automated process

    Examples
    --------
    Basic UI takeover for CAPTCHA solving:

    >>> from amzn_nova_act_human_intervention_client import (
    ...     UITakeoverInterventionExecutor,
    ...     AssumedRoleCredentialsProvider
    ... )
    >>> from amzn_nova_act_human_intervention_common import (
    ...     UITakeoverRequest,
    ...     BrowserSessionContext,
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
    >>> executor = UITakeoverInterventionExecutor(
    ...     endpoint="wss://myapi.execute-api.us-west-2.amazonaws.com/prod",
    ...     intervention_context=context,
    ...     credentials_provider=credentials,
    ...     region="us-west-2"
    ... )
    >>>
    >>> # Create UI takeover request
    >>> browser_session = BrowserSessionContext(session_id="browser-session-123")
    >>> takeover = UITakeoverRequest(
    ...     message="Please solve the CAPTCHA on the login page",
    ...     browser_session=browser_session,
    ...     notification_recipients=[
    ...         EmailContactInfo(email="operator@example.com")
    ...     ]
    ... )
    >>>
    >>> # Execute and wait for human to complete the task
    >>> executor.run(takeover)
    >>> print(executor.completion_response)
    {'type': 'workflow_completed', 'executionStatus': 'SUCCEEDED'}

    UI takeover with custom timeout:

    >>> # Create executor with 30-minute timeout
    >>> executor = UITakeoverInterventionExecutor(
    ...     endpoint="wss://myapi.execute-api.us-west-2.amazonaws.com/prod",
    ...     intervention_context=context,
    ...     credentials_provider=credentials,
    ...     execution_timeout=1800  # 30 minutes
    ... )
    >>>
    >>> takeover = UITakeoverRequest(
    ...     message="Please complete the multi-step verification process",
    ...     browser_session=browser_session,
    ...     notification_recipients=[
    ...         EmailContactInfo(email="operator@example.com")
    ...     ]
    ... )
    >>>
    >>> executor.run(takeover)

    Handling UI takeover errors:

    >>> from amzn_nova_act_human_intervention_client import WorkflowExecutionError
    >>>
    >>> try:
    ...     executor.run(takeover)
    ...     print(f"Task completed: {executor.completion_response['executionStatus']}")
    ... except WorkflowExecutionError as e:
    ...     print(f"Workflow was terminated by user: {e.message}")
    ... except RuntimeError as e:
    ...     print(f"Workflow failed: {e}")
    """

    def _create_message(self, input_data: UITakeoverRequest) -> Dict[str, Any]:
        """Create UI takeover message.

        Args:
            input_data: UI takeover request data

        Returns:
            WebSocket message for UI takeover
        """
        ui_input = UITakeoverStepFunctionInput(
            timeout=self._execution_timeout,
            workflow_run_id=self._intervention_context.workflow_run_id,
            session_id=self._intervention_context.act_session_id,
            act_id=self._intervention_context.act_id,
            event_id=str(uuid.uuid4()),
            type=UseCase.UI_TAKEOVER,
            message=input_data.message,
            remote_browser=BrowserSessionContext(session_id=input_data.browser_session.session_id),
            notification_recipients=input_data.notification_recipients,
        )

        message = ExecutorRequest(action=self._execution_action_name, input=ui_input)
        return message.model_dump(mode="json")

    def _on_message(self, app: WebSocket, message: str) -> None:
        """Handle incoming WebSocket messages for UI takeover workflow.

        Args:
            app: WebSocket connection
            message: Raw message string received from server
        """
        if Utils.is_valid_json(message):
            rcvd_message: GenericDict = json.loads(message)
            message_type = rcvd_message.get("type")

            if message_type == "workflow_started":
                self.logger.info(f"[UI Takeover Workflow Started] Event ID: {rcvd_message.get('eventId')}")
                self.logger.info(f"  Workflow Run ID: {rcvd_message.get('workflowRunId')}")
                self.logger.info(f"  Session ID: {rcvd_message.get('sessionId')}")
                self.logger.info(f"  SPA URL: {rcvd_message.get('spaUrl')}")
                self.logger.info(f"  Message: {rcvd_message.get('message')}")

                self._is_reconnecting = False  # Reset reconnection flag on successful message

            elif message_type == "workflow_completed":
                execution_status = rcvd_message.get("executionStatus")

                self.logger.info(f"[UI Takeover Workflow Completed] Event ID: {rcvd_message.get('eventId')}")
                self.logger.info(f"  Execution Status: {execution_status}")
                self.logger.info(f"  Message: {rcvd_message.get('message')}")

                self._completion_received = True
                self.completion_response = rcvd_message
                self._handle_completion(app, rcvd_message)

                # Store exception for failed workflows to re-raise after event loop
                # WorkflowExecutionError only for TERMINATED status
                # RuntimeError for FAILED or null/missing executionStatus
                if execution_status is None:
                    error_msg = "UI Takeover workflow completed with null executionStatus"
                    self.logger.error(error_msg)
                    self._exception = RuntimeError(error_msg)
                elif execution_status == ExecutionStatus.TERMINATED.value:
                    additional_message = rcvd_message.get("message")
                    self.logger.error(f"UI Takeover workflow terminated: {execution_status}")
                    self._exception = WorkflowExecutionError(
                        status=ExecutionStatus.TERMINATED,
                        workflow_type="UI Takeover",
                        message=additional_message,
                    )
                elif execution_status == ExecutionStatus.FAILED.value:
                    error_msg = f"UI Takeover workflow failed with status: {execution_status}"
                    additional_message = rcvd_message.get("message")
                    if additional_message:
                        error_msg = f"{error_msg} - {additional_message}"
                    self.logger.error(error_msg)
                    self._exception = RuntimeError(error_msg)

            else:
                self.logger.info(f"UI Takeover message received: {rcvd_message}")
