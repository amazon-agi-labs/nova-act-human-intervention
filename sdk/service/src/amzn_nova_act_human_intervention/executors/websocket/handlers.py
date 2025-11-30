import os

from amzn_nova_act_human_intervention_common import JSONType
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.executors.websocket.service import WebSocketService


class ServiceManager:
    """Manages WebSocket service instance using singleton pattern.

    Provides lazy initialization of WebSocketService to optimize Lambda cold starts
    and ensure environment variables are available during service creation.

    Attributes:
        _instance: Class-level WebSocketService instance, None until first access
    """

    _instance: WebSocketService | None = None

    @classmethod
    def get_service(cls) -> WebSocketService:
        """Get or create the WebSocket service instance.

        Uses lazy initialization to create the service only when first needed.
        Subsequent calls return the same instance for optimal performance.

        Returns:
            WebSocketService: Configured WebSocket service instance

        Raises:
            EnvironmentError: If EXECUTOR_ENDPOINT environment variable is not set
        """
        if cls._instance is None:
            endpoint = os.environ.get("EXECUTOR_ENDPOINT")
            if not endpoint:
                raise EnvironmentError("EXECUTOR_ENDPOINT environment variable must be set")
            cls._instance = WebSocketService(endpoint=endpoint)
        return cls._instance


@event_source(data_class=APIGatewayProxyEvent)
def websocket_connect(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for WebSocket connect events.

    Args:
        event: API Gateway WebSocket connection event
        context: Lambda execution context

    Returns:
        WebSocket response dictionary
    """
    return ServiceManager.get_service().handle_connect(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def websocket_disconnect(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for WebSocket disconnect events.

    Args:
        event: API Gateway WebSocket disconnection event
        context: Lambda execution context

    Returns:
        WebSocket response dictionary
    """
    return ServiceManager.get_service().handle_disconnect(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def start_hitl_flow(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for WebSocket HITL flow events (start-hitl-flow and $default routes).

    Args:
        event: API Gateway WebSocket message event
        context: Lambda execution context

    Returns:
        WebSocket response dictionary
    """
    return ServiceManager.get_service().handle_start_hitl_flow(event, context)


@event_source(data_class=APIGatewayProxyEvent)
def connection_refresh(event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for WebSocket connection refresh events.

    Updates the connectionId in DynamoDB when client reconnects with a new WebSocket URL
    after the previous URL expired during long-running executions.

    Args:
        event: API Gateway WebSocket message event containing new connectionId
        context: Lambda execution context

    Returns:
        WebSocket response dictionary
    """
    return ServiceManager.get_service().handle_connection_refresh(event, context)
