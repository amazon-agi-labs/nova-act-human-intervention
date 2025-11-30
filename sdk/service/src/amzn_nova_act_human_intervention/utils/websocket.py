"""WebSocket utility functions for sending messages to API Gateway connections."""

import json
import os
import traceback

import boto3
from amzn_nova_act_human_intervention_common import GenericDict, LoggingConfig

logger = LoggingConfig.get_logger(__name__)


def send_websocket_message(endpoint: str, connection_id: str, message: GenericDict) -> None:
    """Send a message to a WebSocket connection via API Gateway Management API.

    Args:
        endpoint: The API Gateway management API endpoint.
        connection_id: The WebSocket connection ID
        message: Dictionary to send as JSON message

    Raises:
        Exception: If message sending fails (logged but not raised)

    Example:
        >>> send_websocket_message(
        ...     endpoint="wss://...",
        ...     connection_id="abc123",
        ...     message={
        ...         "type": "workflow_started",
        ...         "eventId": "event-123",
        ...         "message": "Workflow started successfully"
        ...     }
        ... )
    """
    try:
        # Convert wss:// to https:// for API Gateway Management API
        # Format: wss://abc123.execute-api.region.amazonaws.com/stage
        # Becomes: https://abc123.execute-api.region.amazonaws.com/stage
        api_endpoint = endpoint.replace("wss://", "https://").replace("ws://", "http://")

        # Create API Gateway Management API client
        apigw_management = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=api_endpoint,
            region_name=os.environ.get("AWS_REGION"),
        )

        # Send message to connection
        apigw_management.post_to_connection(ConnectionId=connection_id, Data=json.dumps(message).encode("utf-8"))

        logger.info(f"Sent WebSocket message to connection {connection_id}: {message.get('type')}")

    except Exception as e:
        # Check if it's a GoneException by error code for ClientError
        if (
            hasattr(e, "response")
            and isinstance(e.response, dict)
            and e.response.get("Error", {}).get("Code") == "GoneException"
        ):
            logger.warning(f"WebSocket connection {connection_id} is gone")
        else:
            logger.error(f"Failed to send WebSocket message to {connection_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
