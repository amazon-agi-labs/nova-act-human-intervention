import json
import os
import time
import traceback
from datetime import datetime
from http import HTTPStatus

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
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from bedrock_agentcore.tools.browser_client import DEFAULT_IDENTIFIER, BrowserClient

from amzn_nova_act_human_intervention.models import LambdaResponse
from amzn_nova_act_human_intervention.workflows.base_handlers import BaseApiHandler

logger = LoggingConfig.get_logger(__name__)


class UITakeoverApiHandler(BaseApiHandler):
    """UI Takeover API handler implementation."""

    def get_browser_session_info(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        def _clean_ac_response_data(data: JSONType) -> JSONType:
            """Remove ResponseMetadata and convert datetime objects to strings"""
            if isinstance(data, datetime):
                return data.isoformat()
            elif isinstance(data, dict):
                return {k: _clean_ac_response_data(v) for k, v in data.items() if k != "ResponseMetadata"}
            elif isinstance(data, list):
                return [_clean_ac_response_data(item) for item in data]
            return data

        """Get browser session information for UI takeover."""
        # Parameters come from request body (token-based auth approach)
        try:
            body = json.loads(event.body) if event.body else {}
        except json.JSONDecodeError:
            return LambdaResponse.error(
                HTTPStatus.BAD_REQUEST, body={"error": "Invalid JSON in request body"}
            ).for_api_gateway()

        token = body.get("token")
        if not token:
            return LambdaResponse.error(HTTPStatus.BAD_REQUEST, body={"error": "Token is required"}).for_api_gateway()

        # remote_browser comes from request body
        remote_browser = body.get("remote_browser")
        if not remote_browser:
            return LambdaResponse.error(
                HTTPStatus.BAD_REQUEST, body={"error": "Remote browser info is required"}
            ).for_api_gateway()

        try:
            agent_core_session_id = remote_browser.get("session_id")
        except AttributeError:
            return LambdaResponse.error(
                HTTPStatus.BAD_REQUEST, body={"error": "Invalid remote_browser format"}
            ).for_api_gateway()

        if not agent_core_session_id:
            return LambdaResponse.error(
                HTTPStatus.BAD_REQUEST, body={"error": "Remote browser session ID is required"}
            ).for_api_gateway()

        aws_region = os.environ.get("AWS_REGION")
        if not aws_region:
            raise ValueError("AWS_REGION environment variable must be set")

        agent_core_browser = BrowserClient(region=aws_region)
        agent_core_browser.identifier = DEFAULT_IDENTIFIER
        agent_core_browser.session_id = agent_core_session_id
        get_browser_session_response: GenericDict = agent_core_browser.client.get_browser_session(
            browserIdentifier=DEFAULT_IDENTIFIER,
            sessionId=agent_core_session_id,
        )
        if get_browser_session_response["status"] == "TERMINATED":
            # Update execution item with browser termination error
            try:
                dynamodb = boto3.resource("dynamodb", region_name=aws_region)
                executions_table = dynamodb.Table(os.environ["EXECUTIONS_TABLE"])

                # Get event ID from token
                event_id = body.get("token", "")
                if event_id:
                    error_details = ErrorDetails.from_error_code(ErrorCode.BROWSER_SESSION_TERMINATED)
                    executions_table.update_item(
                        Key={"eventId": event_id},
                        UpdateExpression="SET executionStatus = :status, "
                        "updatedAt = :updated_at, "
                        "errorDetails = :error_details",
                        ExpressionAttributeValues={
                            ":status": ExecutionStatus.FAILED.value,
                            ":updated_at": int(time.time()),
                            ":error_details": error_details.model_dump(),
                        },
                    )
                    logger.info(f"Updated execution {event_id} with BROWSER_SESSION_TERMINATED error")
            except Exception as e:
                logger.error(f"Failed to update execution with browser termination error: {e}")

            # Always raise exception to fail the Step Function execution
            raise RuntimeError("Remote browser has been terminated")
        presigned_live_stream_url: str = agent_core_browser.generate_live_view_url().strip()
        agent_core_browser_session = _clean_ac_response_data(get_browser_session_response)

        # Type narrowing: agent_core_browser_session should be a dict after _clean_ac_response_data
        if not isinstance(agent_core_browser_session, dict):
            raise TypeError("Expected dict from _clean_ac_response_data")

        response_data: dict = agent_core_browser_session.copy()  # type: ignore[assignment]

        if not isinstance(response_data.get("streams"), dict):
            raise TypeError("Expected streams to be dict")
        if not isinstance(response_data["streams"].get("liveViewStream"), dict):
            raise TypeError("Expected liveViewStream to be dict")

        response_data["streams"]["liveViewStream"]["presignedUrl"] = presigned_live_stream_url

        return LambdaResponse.success(body=response_data).for_api_gateway()

    def complete_task_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Handle UI takeover task completion."""
        try:
            # Parameters come from request body (token-based auth approach)
            try:
                body = json.loads(event.body) if event.body else {}
            except json.JSONDecodeError:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Invalid JSON in request body"}
                ).for_api_gateway()

            # Get eventId from token
            event_id = body.get("token", "")
            if not event_id:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Token is required"}
                ).for_api_gateway()

            # Get execution info from DynamoDB for notification purposes
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION"))
            executions_table = dynamodb.Table(os.environ["EXECUTIONS_TABLE"])
            response = executions_table.get_item(Key={"eventId": event_id})

            if "Item" not in response:
                return LambdaResponse.error(HTTPStatus.NOT_FOUND, body={"error": "Task not found"}).for_api_gateway()

            execution_item = ExecutionItem(**response["Item"])

            # Atomic update with condition to prevent replay attacks and race conditions
            # Only update if status is PENDING_HUMAN_INPUT (not in terminal state)
            try:
                executions_table.update_item(
                    Key={"eventId": event_id},
                    UpdateExpression="SET executionStatus = :status, updatedAt = :updated_at",
                    ConditionExpression="executionStatus = :pending_status",
                    ExpressionAttributeValues={
                        ":status": ExecutionStatus.COMPLETED.value,
                        ":updated_at": int(time.time()),
                        ":pending_status": ExecutionStatus.PENDING_HUMAN_INPUT.value,
                    },
                )
            except executions_table.meta.client.exceptions.ConditionalCheckFailedException:
                # Status is not PENDING_HUMAN_INPUT - task already completed or in terminal state
                logger.warning(
                    f"Conditional update failed for task {event_id}. "
                    f"Task is already completed or in terminal state. "
                    f"Current status: {execution_item.executionStatus.value}"
                )
                return LambdaResponse.error(
                    HTTPStatus.CONFLICT,
                    body={
                        "error": "Task is already completed",
                        "currentStatus": execution_item.executionStatus.value,
                    },
                ).for_api_gateway()

            logger.info(f"Task completed for eventId {event_id}")

            # Send task completion notification
            try:
                self._notification_factory.send_task_completion_notification(execution_item)
            except Exception as e:
                logger.warning(f"Failed to send task completion notification: {str(e)}")

            return LambdaResponse.success(
                body={"message": "Task completed successfully", "task_completed": True}
            ).for_api_gateway()

        except Exception as e:
            logger.error(f"Error in complete_task_handler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return LambdaResponse.error(
                HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Internal server error"}
            ).for_api_gateway()

    def task_status_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Get UI takeover task status."""
        try:
            # Parameters come from request body (token-based auth approach)
            try:
                body = json.loads(event.body) if event.body else {}
            except json.JSONDecodeError:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Invalid JSON in request body"}
                ).for_api_gateway()

            # Get eventId from token
            event_id = body.get("token", "")
            if not event_id:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Token is required"}
                ).for_api_gateway()

            # Get task status from DynamoDB
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION"))
            table = dynamodb.Table(os.environ["EXECUTIONS_TABLE"])
            response = table.get_item(Key={"eventId": event_id})

            if "Item" not in response:
                return LambdaResponse.error(HTTPStatus.NOT_FOUND, body={"error": "Task not found"}).for_api_gateway()

            execution_item = ExecutionItem(**response["Item"])
            task_completed = execution_item.executionStatus.is_terminal()

            response_body: GenericDict = {
                "task_completed": task_completed,
                "executionStatus": execution_item.executionStatus.value,
                "updatedAt": execution_item.updatedAt,
            }

            # Include error details if present
            if execution_item.errorDetails:
                response_body["errorDetails"] = execution_item.errorDetails

            return LambdaResponse.success(body=response_body).for_api_gateway()

        except Exception as e:
            logger.error(f"Error in task_status_handler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return LambdaResponse.error(
                HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Internal server error"}
            ).for_api_gateway()

    def terminate_workflow_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Handle UI takeover workflow termination.

        Stops the Step Functions execution. The completion_handler will receive an EventBridge
        event and update the DynamoDB table with the final status.
        """
        try:
            # Parameters come from request body (token-based auth approach)
            try:
                body = json.loads(event.body) if event.body else {}
            except json.JSONDecodeError:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Invalid JSON in request body"}
                ).for_api_gateway()

            # Get eventId from token
            event_id = body.get("token", "")
            if not event_id:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Token is required"}
                ).for_api_gateway()

            # Get execution info from DynamoDB to retrieve executionArn
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION"))
            table = dynamodb.Table(os.environ["EXECUTIONS_TABLE"])
            response = table.get_item(Key={"eventId": event_id})

            if "Item" not in response:
                return LambdaResponse.error(
                    HTTPStatus.NOT_FOUND, body={"error": "Workflow not found"}
                ).for_api_gateway()

            execution_item = ExecutionItem(**response["Item"])
            if not execution_item.executionArn:
                return LambdaResponse.error(
                    HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Execution ARN not found"}
                ).for_api_gateway()

            # Check if task is already completed - don't allow termination of completed tasks
            # This prevents overwriting user completion with TERMINATED
            if execution_item.executionStatus.is_terminal():
                logger.warning(
                    f"Cannot terminate already completed task {event_id}. "
                    f"Current status: {execution_item.executionStatus.value}"
                )
                return LambdaResponse.error(
                    HTTPStatus.CONFLICT,
                    body={
                        "error": "Cannot terminate completed task",
                        "currentStatus": execution_item.executionStatus.value,
                    },
                ).for_api_gateway()

            # Stop the Step Functions execution
            # EventBridge will trigger completion_handler which will update DynamoDB
            stepfunctions = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION"))
            stepfunctions.stop_execution(
                executionArn=execution_item.executionArn,
                error="UserTerminated",
                cause=f"User terminated workflow via SPA for eventId: {event_id}",
            )

            logger.info(
                f"Stopped Step Functions execution for eventId {event_id}, executionArn: {execution_item.executionArn}"
            )

            # Send termination notification
            try:
                self._notification_factory.send_termination_notification(execution_item)
            except Exception as e:
                logger.warning(f"Failed to send termination notification: {str(e)}")

            return LambdaResponse.success(
                body={"message": "Workflow termination requested", "workflow_terminated": True}
            ).for_api_gateway()

        except Exception as e:
            logger.error(f"Error in terminate_workflow_handler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return LambdaResponse.error(
                HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Internal server error"}
            ).for_api_gateway()

    def view_details_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Get workflow details including actId, workflowRunId, sessionId, and expirationTime."""
        try:
            # Parameters come from request body (token-based auth approach)
            try:
                body = json.loads(event.body) if event.body else {}
            except json.JSONDecodeError:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Invalid JSON in request body"}
                ).for_api_gateway()

            # Get eventId from token
            event_id = body.get("token", "")
            if not event_id:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": "Token is required"}
                ).for_api_gateway()

            # Get workflow details from DynamoDB
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION"))
            table = dynamodb.Table(os.environ["EXECUTIONS_TABLE"])
            response = table.get_item(Key={"eventId": event_id})

            if "Item" not in response:
                return LambdaResponse.error(
                    HTTPStatus.NOT_FOUND, body={"error": "Workflow not found"}
                ).for_api_gateway()

            execution_item = ExecutionItem(**response["Item"])

            # Calculate expiration time from TTL
            expiration_time = None
            if execution_item.ttl:
                expiration_time = datetime.fromtimestamp(int(execution_item.ttl)).isoformat()

            return LambdaResponse.success(
                body={
                    "actId": execution_item.actId,
                    "workflowRunId": execution_item.workflowRunId,
                    "sessionId": execution_item.sessionId,
                    "eventId": event_id,
                    "expirationTime": expiration_time,
                    "executionStatus": execution_item.executionStatus.value,
                    "interventionType": execution_item.interventionType.value,
                }
            ).for_api_gateway()

        except Exception as e:
            logger.error(f"Error in view_details_handler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return LambdaResponse.error(
                HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Internal server error"}
            ).for_api_gateway()


@event_source(data_class=APIGatewayProxyEvent)
def browser_session_info_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for browser session info."""
    return UITakeoverApiHandler().get_browser_session_info(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def complete_task_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for task completion."""
    return UITakeoverApiHandler().complete_task_handler(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def task_status_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for task status."""
    return UITakeoverApiHandler().task_status_handler(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def terminate_workflow_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for workflow termination."""
    return UITakeoverApiHandler().terminate_workflow_handler(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def view_details_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for viewing workflow details."""
    return UITakeoverApiHandler().view_details_handler(event, context)
