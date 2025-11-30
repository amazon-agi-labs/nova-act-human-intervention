import os
import time
import traceback
from abc import ABC, abstractmethod

import boto3
from amzn_nova_act_human_intervention_common import (
    ErrorCode,
    ErrorDetails,
    ExecutionItem,
    ExecutionStatus,
    GenericDict,
    JSONType,
    LoggingConfig,
)
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent, EventBridgeEvent
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.notifications import NotificationDeliveryError, NotificationFactory
from amzn_nova_act_human_intervention.utils import send_websocket_message

logger = LoggingConfig.get_logger(__name__)


class BaseWorkflowHandler(ABC):
    """Base class for workflow handlers with common functionality.

    Provides common implementations for workflow operations that are shared
    between Approval and UI Takeover workflows.
    """

    def __init__(self) -> None:
        """Initialize common resources for all workflow handlers."""
        self._current_boto_session = boto3.Session()
        self._s3_client = self._current_boto_session.client("s3")
        self._dynamodb_client = self._current_boto_session.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION")
        )
        self._notification_factory = NotificationFactory()

    @abstractmethod
    def handle_spa_generator(self, event: GenericDict, context: LambdaContext) -> JSONType:
        """Generate SPA for the workflow (workflow-specific implementation required)."""

    def handle_confirm_if_answered(self, event: GenericDict, context: LambdaContext) -> bool:
        """Check if workflow task has been answered.

        Common implementation that checks if the execution status is COMPLETED or TERMINATED.

        Args:
            event: Step Function input containing event_id
            context: Lambda execution context

        Returns:
            Boolean indicating whether the task has been answered

        Example:
            >>> handler = MyWorkflowHandler()
            >>> event = {"event_id": "e4b232ed-ddc6-40bf-b61f-4e62da0c3f2a"}
            >>> is_answered = handler.handle_confirm_if_answered(event, context)
            >>> is_answered
            True
        """
        try:
            event_id = event.get("event_id")
            if not event_id:
                logger.error("Missing event_id in event")
                return False

            executions_table = self._dynamodb_client.Table(os.environ["EXECUTIONS_TABLE"])
            response = executions_table.get_item(Key={"eventId": event_id})

            if "Item" not in response:
                logger.warning(
                    f"Execution item not found for event_id: {event_id}. "
                    "Item likely expired via TTL. Treating as completed to stop polling."
                )
                return True

            execution_item = ExecutionItem(**response["Item"])
            is_answered: bool = execution_item.executionStatus.is_terminal()

            logger.info(f"Execution status for {event_id}: {execution_item.executionStatus}, answered: {is_answered}")
            return is_answered

        except Exception as e:
            logger.error(f"Error in handle_confirm_if_answered: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def handle_completion(self, event: EventBridgeEvent, context: LambdaContext) -> JSONType:
        """Handle workflow completion.

        Common implementation that processes Step Functions execution status changes
        and updates the DynamoDB execution record.

        Args:
            event: EventBridge event containing Step Functions execution status
            context: Lambda execution context

        Returns:
            Dictionary containing processing result

        Examples of event.detail structure:

        FAILED status with NotificationDeliveryError:
            {
              "executionArn": "arn:aws:states:us-east-1:298680963092:execution:
                              NovaActUITakeoverWorkflow-test:ede984e7-29b5-46ee-8f80-f3b5203e5c84",
              "stateMachineArn": "arn:aws:states:us-east-1:298680963092:stateMachine:
                                  NovaActUITakeoverWorkflow-test",
              "name": "ede984e7-29b5-46ee-8f80-f3b5203e5c84",
              "status": "FAILED",
              "startDate": 1762653894590,
              "stopDate": 1762653900164,
              "input": "{\\"workflow_run_id\\": \\"550e8400-e29b-41d4-a716-446655440000\\", ...}",
              "output": null,
              "error": "NotificationDeliveryError",
              "cause": "{\\"errorMessage\\":\\"Notification delivery failed for channels: EMAIL:
                        An error occurred (MessageRejected) when calling the SendEmail operation:
                        Email address is not verified...\\",\\"errorType\\":\\"NotificationDeliveryError\\",
                        \\"requestId\\":\\"5193a54f-79ba-4792-bef5-74eec81c836e\\",\\"stackTrace\\":[...]}"
            }

        SUCCEEDED status:
            {
              "executionArn": "arn:aws:states:us-east-1:123456789012:execution:
                              NovaActApprovalWorkflow:abc123",
              "stateMachineArn": "arn:aws:states:us-east-1:123456789012:stateMachine:
                                  NovaActApprovalWorkflow",
              "name": "abc123",
              "status": "SUCCEEDED",
              "startDate": 1762653894590,
              "stopDate": 1762653900164,
              "input": "{\\"workflow_run_id\\": \\"550e8400-e29b-41d4-a716-446655440000\\", ...}",
              "output": "{\\"statusCode\\": 200, \\"body\\": \\"{\\\\\\"message\\\\\\":
                        \\\\\\"Approval request sent successfully\\\\\\"}\\"}",
              "error": null,
              "cause": null
            }

        ABORTED status (user terminated):
            {
              "executionArn": "arn:aws:states:us-east-1:123456789012:execution:
                              NovaActUITakeoverWorkflow:xyz789",
              "stateMachineArn": "arn:aws:states:us-east-1:123456789012:stateMachine:
                                  NovaActUITakeoverWorkflow",
              "name": "xyz789",
              "status": "ABORTED",
              "startDate": 1762653894590,
              "stopDate": 1762653900164,
              "input": "{\\"workflow_run_id\\": \\"550e8400-e29b-41d4-a716-446655440000\\", ...}",
              "output": null,
              "error": "UserTerminated",
              "cause": "User terminated workflow via SPA for eventId: xyz789"
            }

        TIMED_OUT status:
            {
              "executionArn": "arn:aws:states:us-east-1:123456789012:execution:
                              NovaActApprovalWorkflow:def456",
              "stateMachineArn": "arn:aws:states:us-east-1:123456789012:stateMachine:
                                  NovaActApprovalWorkflow",
              "name": "def456",
              "status": "TIMED_OUT",
              "startDate": 1762653894590,
              "stopDate": 1762661094590,
              "input": "{\\"workflow_run_id\\": \\"550e8400-e29b-41d4-a716-446655440000\\", ...}",
              "output": null,
              "error": "States.Timeout",
              "cause": "Execution timed out after configured timeout"
            }
        """
        try:
            if not event or not event.detail:
                logger.error("Invalid event: missing detail")
                return {"error": "Invalid event"}

            execution_arn = event.detail.get("executionArn")
            status = event.detail.get("status")

            if not execution_arn or not status:
                logger.error("Missing execution ARN or status")
                return {"error": "Missing required fields"}

            logger.info(f"Processing workflow completion: {execution_arn}, status: {status}")

            # Get execution name from ARN
            execution_name = execution_arn.split(":")[-1]

            executions_table = self._dynamodb_client.Table(os.environ["EXECUTIONS_TABLE"])
            response = executions_table.get_item(Key={"eventId": execution_name})

            if "Item" not in response:
                logger.warning(f"Execution item not found for execution: {execution_name}")
                return {"status": "execution_not_found", "executionArn": execution_arn}

            # Map Step Functions execution status to workflow status
            execution_status_map = {
                "SUCCEEDED": ExecutionStatus.COMPLETED.value,
                "ABORTED": ExecutionStatus.TERMINATED.value,
                "FAILED": ExecutionStatus.FAILED.value,
                "TIMED_OUT": ExecutionStatus.FAILED.value,
            }
            execution_status = execution_status_map.get(status, ExecutionStatus.FAILED.value)

            # Determine error details for FAILED status
            if execution_status == ExecutionStatus.FAILED.value:
                logger.error(f"Event details: {event.detail}")

                # Map Step Functions status to error codes
                if status == "TIMED_OUT":
                    error_details = ErrorDetails.from_error_code(ErrorCode.TIMEOUT)
                else:
                    # Check error cause to determine specific error type
                    error: str = event.detail.get("error", "")
                    cause: str = event.detail.get("cause", "")

                    # Check if notification delivery failed by looking for NotificationDeliveryError
                    if error == NotificationDeliveryError.__name__ or NotificationDeliveryError.__name__ in cause:
                        error_details = ErrorDetails.from_error_code(ErrorCode.NOTIFICATION_FAILED)
                    else:
                        # For generic FAILED status, use EXECUTION_FAILED
                        error_details = ErrorDetails.from_error_code(ErrorCode.EXECUTION_FAILED)

                # Update execution item with error details
                # Use conditional update to not overwrite user-driven COMPLETED status
                try:
                    executions_table.update_item(
                        Key={"eventId": execution_name},
                        UpdateExpression="SET executionStatus = :execution_status,"
                        "updatedAt = :updated_at,"
                        "errorDetails = :error_details",
                        ConditionExpression="executionStatus <> :completed_status",
                        ExpressionAttributeValues={
                            ":execution_status": execution_status,
                            ":updated_at": int(time.time()),
                            ":error_details": error_details.model_dump(),
                            ":completed_status": ExecutionStatus.COMPLETED.value,
                        },
                    )
                except executions_table.meta.client.exceptions.ConditionalCheckFailedException:
                    logger.info(
                        f"Skipping status update for {execution_name} - "
                        f"task already completed (user decision takes precedence)"
                    )
            else:
                # Update execution item without error details
                # Use conditional update to not overwrite user-driven COMPLETED status
                try:
                    executions_table.update_item(
                        Key={"eventId": execution_name},
                        UpdateExpression="SET executionStatus = :execution_status, updatedAt = :updated_at",
                        ConditionExpression="executionStatus <> :completed_status",
                        ExpressionAttributeValues={
                            ":execution_status": execution_status,
                            ":updated_at": int(time.time()),
                            ":completed_status": ExecutionStatus.COMPLETED.value,
                        },
                    )
                except executions_table.meta.client.exceptions.ConditionalCheckFailedException:
                    logger.info(
                        f"Skipping status update for {execution_name} - "
                        f"task already completed (user decision takes precedence)"
                    )

            logger.info(f"Updated execution {execution_name} with executionStatus={execution_status}")

            # Notify WebSocket client
            try:
                execution_item = ExecutionItem(**response["Item"])
                if execution_item.connectionId:
                    # Base message with common fields
                    message = {
                        "type": "workflow_completed",
                        "eventId": execution_name,
                        "executionArn": execution_arn,
                        "executionStatus": execution_status,
                        "message": f"Workflow completed with status: {execution_status}",
                    }

                    # Add workflow-specific fields via hook
                    additional_fields = self._get_completion_message_fields(execution_item)
                    message.update(additional_fields)

                    send_websocket_message(
                        endpoint=execution_item.executionEndpoint,
                        connection_id=execution_item.connectionId,
                        message=message,
                    )
            except Exception as e:
                logger.warning(f"Failed to send workflow completed message: {str(e)}")

            return {
                "status": "success",
                "executionArn": execution_arn,
                "executionStatus": execution_status,
                "message": f"Processed execution {execution_arn} with status {execution_status}",
            }

        except Exception as e:
            logger.error(f"Error in handle_completion: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"error": "Internal server error", "message": str(e)}

    def _get_completion_message_fields(self, execution_item: ExecutionItem) -> dict:
        """Hook for subclasses to add workflow-specific fields to completion message.

        Args:
            execution_item: The execution item from DynamoDB

        Returns:
            Dictionary of additional fields to include in the WebSocket completion message
        """
        return {}


class BaseApiHandler(ABC):
    """Base class for API handlers."""

    def __init__(self) -> None:
        self._notification_factory = NotificationFactory()

    @abstractmethod
    def get_browser_session_info(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Get browser session information."""

    @abstractmethod
    def complete_task_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Handle task completion."""

    @abstractmethod
    def task_status_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Get task status."""
