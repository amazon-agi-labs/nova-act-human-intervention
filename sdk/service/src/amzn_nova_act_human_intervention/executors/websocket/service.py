import json
import os
import traceback
from http import HTTPStatus

import boto3
from amzn_nova_act_human_intervention_common import (
    ConnectionItem,
    ExecutionItem,
    ExecutorRequest,
    JSONType,
    StepFunctionInput,
)
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.constants import DEFAULT_CONNECTION_TTL_SECONDS
from amzn_nova_act_human_intervention.executors.base import BaseInterventionExecutor
from amzn_nova_act_human_intervention.models import LambdaResponse


class WebSocketService(BaseInterventionExecutor):
    """WebSocket-based implementation of human intervention executor.

    Provides real-time WebSocket communication for human intervention in automated processes.
    Manages the complete connection lifecycle including establishment, message routing, and cleanup.
    Persists connection state in DynamoDB with automatic TTL-based cleanup.

    The service integrates with AWS API Gateway WebSocket APIs and uses DynamoDB for
    connection tracking. Each connection is stored with a configurable TTL to ensure
    automatic cleanup of stale connections.

    Environment Variables:
        CONNECTIONS_TABLE: DynamoDB table name for storing connection metadata

    Attributes:
        dynamodb: Boto3 DynamoDB resource for connection persistence
        connections_table: DynamoDB table for storing WebSocket connections

    Example:
        >>> service = WebSocketService("wss://api.example.com/prod")
        >>> response = service.handle_connect(event, context)
        >>> print(response['statusCode'])  # 200
    """

    def __init__(self, endpoint: str) -> None:
        """Initialize WebSocket service with AWS resource connections.

        Sets up DynamoDB table connection for persistence and API Gateway client
        for WebSocket message delivery. Validates the endpoint URL format.

        Args:
            endpoint: WebSocket API Gateway endpoint URL (must start with ws:// or wss://)

        Raises:
            ValueError: If endpoint is not a valid WebSocket URL
            KeyError: If CONNECTIONS_TABLE environment variable is not set

        Environment Variables Required:
            CONNECTIONS_TABLE: Name of DynamoDB table for connection storage
        """
        super().__init__(endpoint)
        self.dynamodb = boto3.resource("dynamodb")
        self.stepfunctions = boto3.client("stepfunctions")
        self.connections_table = self.dynamodb.Table(os.environ["CONNECTIONS_TABLE"])
        self.executions_table = self.dynamodb.Table(os.environ["EXECUTIONS_TABLE"])
        self.state_machine_arns = json.loads(os.environ["STATE_MACHINE_ARNS"])

    def handle_connect(
        self, event: APIGatewayProxyEvent, context: LambdaContext, ttl_seconds: int = DEFAULT_CONNECTION_TTL_SECONDS
    ) -> JSONType:
        """Handle WebSocket connection establishment.

        Processes incoming WebSocket connection requests from API Gateway.
        Validates the connection and persists connection metadata to DynamoDB
        with automatic TTL for cleanup.

        The connection is stored with a timestamp and TTL value to enable
        DynamoDB's automatic item expiration feature for connection cleanup.

        Args:
            event: API Gateway WebSocket connection event containing request context
            context: Lambda execution context (unused but required by interface)
            ttl_seconds: Connection TTL in seconds (default: 86400 = 24 hours)

        Returns:
            Dictionary containing statusCode (200 for success, 4xx/5xx for errors)
            and optional body message. Compatible with API Gateway response format.

        Raises:
            No exceptions raised - all errors are caught and returned as error responses

        Example Response:
            Success: {'statusCode': 200, 'body': None}
            Error: {'statusCode': 400, 'body': 'Missing connection ID'}
        """
        try:
            # Validate event and connection ID
            if not event or not event.request_context:
                self.logger.error("Invalid event: missing request context")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Invalid request context"
                ).for_lambda()

            connection_id = event.request_context.connection_id
            if not connection_id:
                self.logger.error("Missing connection ID")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Missing connection ID"
                ).for_lambda()

            # Validate TTL
            if ttl_seconds <= 0:
                self.logger.error(f"Invalid TTL: {ttl_seconds}")
                return LambdaResponse.error(status_code=HTTPStatus.BAD_REQUEST, body="Invalid TTL value").for_lambda()

            self.logger.info(f"Connecting websocket: {connection_id}")

            # Create and store connection
            connection_item = ConnectionItem.create(connection_id, ttl_seconds)
            self.connections_table.put_item(Item=connection_item.model_dump(exclude_none=True))

            self.logger.info(f"Successfully connected: {connection_id}")
            return LambdaResponse.success().for_lambda()

        except Exception as e:
            self.logger.error(f"Error in handle_connect: {e}\n{traceback.format_exc()}")
            return LambdaResponse.error(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, body="Internal server error"
            ).for_lambda()

    def handle_disconnect(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Handle WebSocket connection termination.

        Processes WebSocket disconnection events from API Gateway.
        Removes the connection record from DynamoDB to clean up connection state.

        Args:
            event: API Gateway WebSocket disconnection event containing connection ID
            context: Lambda execution context (unused but required by interface)

        Returns:
            Dictionary containing statusCode (200 for success, 4xx/5xx for errors)
            and optional body message. Compatible with API Gateway response format.

        Raises:
            No exceptions raised - all errors are caught and returned as error responses

        Example Response:
            Success: {'statusCode': 200, 'body': None}
            Error: {'statusCode': 400, 'body': 'Invalid request context'}
        """
        try:
            # Validate event and connection ID
            if not event or not event.request_context:
                self.logger.error("Invalid event: missing request context")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Invalid request context"
                ).for_lambda()

            connection_id = event.request_context.connection_id
            if not connection_id:
                self.logger.error("Missing connection ID")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Missing connection ID"
                ).for_lambda()

            self.logger.info(f"Disconnecting websocket: {connection_id}")

            # Delete connection from table
            self.connections_table.delete_item(Key={"connectionId": connection_id})

            self.logger.info(f"Successfully disconnected: {connection_id}")
            return LambdaResponse.success().for_lambda()

        except Exception as e:
            self.logger.error(f"Error in handle_disconnect: {e}\n{traceback.format_exc()}")
            return LambdaResponse.error(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, body="Internal server error"
            ).for_lambda()

    def handle_start_hitl_flow(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Handle WebSocket message events for start-hitl-flow and default routes.

        Processes incoming WebSocket messages, validates the connection,
        and invokes Step Functions for HITL flow processing.

        Uses compensating transaction pattern to ensure consistency between
        Step Functions execution and DynamoDB record creation. If DynamoDB
        write fails after Step Functions execution starts, the execution
        is stopped to maintain data consistency.

        Args:
            event: API Gateway WebSocket message event
            context: Lambda execution context

        Returns:
            Dictionary containing statusCode and optional body message
        """
        try:
            if not event or not event.request_context:
                self.logger.error("Invalid event: missing request context")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Invalid request context"
                ).for_lambda()

            connection_id = event.request_context.connection_id
            if not connection_id:
                self.logger.error("Missing connection ID")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Missing connection ID"
                ).for_lambda()

            if event.body is None:
                self.logger.error("Missing payload")
                return LambdaResponse.error(status_code=HTTPStatus.BAD_REQUEST, body="Missing payload").for_lambda()

            # Parse and validate payload
            executor_request: ExecutorRequest = ExecutorRequest.model_validate_json(event.body)
            step_function_input = StepFunctionInput.from_payload(executor_request.input.model_dump())

            # Get state machine ARN for UI takeover
            state_machine_arn = self.state_machine_arns.get(step_function_input.type)
            if not state_machine_arn:
                self.logger.error("UITakeover state machine ARN not configured")
                return LambdaResponse.error(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR, body="State machine not configured"
                ).for_lambda()

            # Start Step Function execution
            execution_response = self.stepfunctions.start_execution(
                stateMachineArn=state_machine_arn,
                name=step_function_input.event_id,
                input=json.dumps(step_function_input.model_dump()),
            )

            try:
                # Create execution record
                execution_item = ExecutionItem.from_step_function_input(
                    event_id=step_function_input.event_id,
                    connection_id=connection_id,
                    execution_arn=execution_response["executionArn"],
                    step_function_input=step_function_input,
                    ttl_seconds=step_function_input.timeout,
                    execution_endpoint=self.endpoint,
                )

                # Store execution record
                self.executions_table.put_item(Item=execution_item.model_dump(exclude_none=True))

            except Exception as db_error:
                # Compensating transaction: stop execution if DynamoDB write fails
                self.logger.error(f"DynamoDB write failed, stopping execution: {db_error}")
                try:
                    self.stepfunctions.stop_execution(
                        executionArn=execution_response["executionArn"],
                        error="DatabaseWriteFailure",
                        cause=str(db_error),
                    )
                except Exception as stop_error:
                    self.logger.error(f"Failed to stop execution during compensation: {stop_error}")
                raise db_error

            self.logger.info(
                f"Started execution {execution_response['executionArn']} for event {step_function_input.event_id}"
            )
            return LambdaResponse.success().for_lambda()

        except Exception as e:
            self.logger.error(f"Error in handle_start_hitl_flow: {e}\n{traceback.format_exc()}")
            return LambdaResponse.error(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, body="Internal server error"
            ).for_lambda()

    def handle_connection_refresh(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        """Handle WebSocket connection refresh during URL expiry.

        Updates the connectionId in DynamoDB when the client reconnects with a new
        WebSocket URL after the previous URL expired. This ensures server-to-client
        messages continue to work during long-running executions.

        Args:
            event: API Gateway WebSocket message event
            context: Lambda execution context

        Returns:
            Dictionary containing statusCode and optional body message
        """
        try:
            if not event or not event.request_context:
                self.logger.error("Invalid event: missing request context")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Invalid request context"
                ).for_lambda()

            new_connection_id = event.request_context.connection_id
            if not new_connection_id:
                self.logger.error("Missing connection ID")
                return LambdaResponse.error(
                    status_code=HTTPStatus.BAD_REQUEST, body="Missing connection ID"
                ).for_lambda()

            if event.body is None:
                self.logger.error("Missing payload")
                return LambdaResponse.error(status_code=HTTPStatus.BAD_REQUEST, body="Missing payload").for_lambda()

            # Parse payload to get event_id
            try:
                payload = json.loads(event.body)
                event_id = payload.get("eventId")
            except json.JSONDecodeError:
                self.logger.error("Invalid JSON in payload")
                return LambdaResponse.error(status_code=HTTPStatus.BAD_REQUEST, body="Invalid JSON").for_lambda()

            if not event_id:
                self.logger.error("Missing eventId in payload")
                return LambdaResponse.error(status_code=HTTPStatus.BAD_REQUEST, body="Missing eventId").for_lambda()

            self.logger.info(f"Refreshing connection for event {event_id}: {new_connection_id}")

            # Update connectionId in ExecutionItem
            try:
                self.executions_table.update_item(
                    Key={"eventId": event_id},
                    UpdateExpression="SET connectionId = :new_connection_id",
                    ExpressionAttributeValues={":new_connection_id": new_connection_id},
                    ConditionExpression="attribute_exists(eventId)",  # Ensure execution exists
                )
                self.logger.info(f"Updated connectionId for event {event_id} to {new_connection_id}")

            except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                self.logger.error(f"Execution not found for event {event_id}")
                return LambdaResponse.error(status_code=HTTPStatus.NOT_FOUND, body="Execution not found").for_lambda()

            return LambdaResponse.success().for_lambda()

        except Exception as e:
            self.logger.error(f"Error in handle_connection_refresh: {e}\n{traceback.format_exc()}")
            return LambdaResponse.error(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, body="Internal server error"
            ).for_lambda()
