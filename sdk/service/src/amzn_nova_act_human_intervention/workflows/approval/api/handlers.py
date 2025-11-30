import json
import os
import time
import traceback
from datetime import datetime
from http import HTTPStatus

import boto3
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ExecutionItem,
    ExecutionStatus,
    GenericDict,
    JSONType,
    LoggingConfig,
)
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.models import LambdaResponse
from amzn_nova_act_human_intervention.workflows.base_handlers import BaseApiHandler

logger = LoggingConfig.get_logger(__name__)


class ApprovalApiHandler(BaseApiHandler):
    """Approval API handler implementation."""

    def record_response_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Record the approval response from the user.

        This endpoint receives the user's approval decision (approve/reject)
        and any additional comments or feedback.
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

            # Get approval action (APPROVE or DENY)
            approval_action = body.get("approvalAction")
            valid_actions = [action.value for action in ApprovalAction]
            if not approval_action or approval_action not in valid_actions:
                return LambdaResponse.error(
                    HTTPStatus.BAD_REQUEST, body={"error": f"approvalAction must be one of {valid_actions}"}
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
            update_data = {
                "executionStatus": ExecutionStatus.COMPLETED.value,
                "updatedAt": int(time.time()),
                "approvalAction": approval_action,
            }

            update_expression = "SET " + ", ".join([f"{k} = :{k}" for k in update_data.keys()])
            expression_attribute_values = {f":{k}": v for k, v in update_data.items()}
            expression_attribute_values[":pending_status"] = ExecutionStatus.PENDING_HUMAN_INPUT.value

            try:
                executions_table.update_item(
                    Key={"eventId": event_id},
                    UpdateExpression=update_expression,
                    ConditionExpression="executionStatus = :pending_status",
                    ExpressionAttributeValues=expression_attribute_values,
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

            logger.info(f"Approval response recorded for eventId {event_id}: action={approval_action}")

            # Send notification based on approval action (approved vs denied)
            try:
                self._notification_factory.send_approval_response_notification(execution_item, approval_action)
            except Exception as e:
                logger.warning(f"Failed to send approval response notification: {str(e)}")

            return LambdaResponse.success(
                body={
                    "message": "Approval response recorded successfully",
                    "approvalAction": approval_action,
                    "task_completed": True,
                }
            ).for_api_gateway()

        except Exception as e:
            logger.error(f"Error in record_response_handler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return LambdaResponse.error(
                HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Internal server error"}
            ).for_api_gateway()

    def task_status_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Get approval task status."""
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

            execution_item: ExecutionItem = ExecutionItem(**response["Item"])
            task_completed = execution_item.executionStatus.is_terminal()

            response_body: GenericDict = {
                "task_completed": task_completed,
                "executionStatus": execution_item.executionStatus.value,
                "approvalAction": execution_item.approvalAction,
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
        """Handle approval workflow termination.

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

            execution_item: ExecutionItem = ExecutionItem(**response["Item"])
            if not execution_item.executionArn:
                return LambdaResponse.error(
                    HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Execution ARN not found"}
                ).for_api_gateway()

            # Check if task is already completed - don't allow termination of completed tasks
            # This prevents overwriting user decisions (APPROVE/DENY) with TERMINATED
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
        """Get workflow details including actId, workflowRunId, and expirationTime."""
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

            execution_item: ExecutionItem = ExecutionItem(**response["Item"])

            # Calculate expiration time from TTL
            expiration_time = None
            if execution_item.ttl:
                expiration_time = datetime.fromtimestamp(int(execution_item.ttl)).isoformat()

            return LambdaResponse.success(
                body={
                    "workflowRunId": execution_item.workflowRunId,
                    "sessionId": execution_item.sessionId,
                    "actId": execution_item.actId,
                    "eventId": execution_item.eventId,
                    "expirationTime": expiration_time,
                    "executionStatus": execution_item.executionStatus.value,
                    "interventionType": execution_item.interventionType.value,
                    "approvalAction": execution_item.approvalAction,
                }
            ).for_api_gateway()

        except Exception as e:
            logger.error(f"Error in view_details_handler: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return LambdaResponse.error(
                HTTPStatus.INTERNAL_SERVER_ERROR, body={"error": "Internal server error"}
            ).for_api_gateway()

    def get_browser_session_info(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        raise NotImplementedError("Method not implemented")

    def complete_task_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        raise NotImplementedError("Method not implemented")


@event_source(data_class=APIGatewayProxyEvent)
def record_response_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for recording approval response."""
    return ApprovalApiHandler().record_response_handler(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def task_status_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for task status."""
    return ApprovalApiHandler().task_status_handler(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def terminate_workflow_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for workflow termination."""
    return ApprovalApiHandler().terminate_workflow_handler(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def view_details_handler(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for viewing workflow details."""
    return ApprovalApiHandler().view_details_handler(event, context)
