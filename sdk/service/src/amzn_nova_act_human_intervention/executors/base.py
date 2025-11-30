"""Base classes for human intervention executors."""

from abc import ABC, abstractmethod
from enum import Enum
from logging import Logger
from typing import Generic, TypeVar

from amzn_nova_act_human_intervention_common import LoggingConfig
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel

# Type variables for generic event and response types
EventT = TypeVar("EventT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)


class ExecutorType(Enum):
    """Available intervention executor implementation types."""

    WEBSOCKET = "websocket"


class BaseInterventionExecutor(ABC, Generic[EventT, ResponseT]):
    """Abstract base class for human intervention executors.

    Defines the interface for executing human intervention processes
    through different communication mechanisms (WebSocket, HTTP, etc.).

    Type Parameters:
        EventT: Pydantic model type for incoming events
        ResponseT: Pydantic model type for responses

    Example:
        >>> class MyExecutor(BaseInterventionExecutor):
        ...     def handle_connect(self, event, context):
        ...         return {"statusCode": 200}
        ...     def handle_disconnect(self, event, context):
        ...         return {"statusCode": 200}
        >>> executor = MyExecutor("wss://api.example.com/prod")
        >>> executor.endpoint
        'wss://api.example.com/prod'
    """

    def __init__(self, endpoint: str) -> None:
        """Initialize the intervention executor.

        Args:
            endpoint: Connection endpoint for the intervention service

        Raises:
            ValueError: If endpoint is not a valid WebSocket URL
        """
        self._validate_websocket_url(endpoint)
        self._endpoint: str = endpoint
        self.logger: Logger = LoggingConfig.get_logger(type(self).__name__)

    def _validate_websocket_url(self, url: str) -> None:
        """Validate that the URL is a valid WebSocket endpoint.

        Args:
            url: URL to validate

        Raises:
            ValueError: If URL is not a valid WebSocket URL
        """
        if not url or not isinstance(url, str):
            raise ValueError("Endpoint must be a non-empty string")

        if not (url.startswith("ws://") or url.startswith("wss://")):
            raise ValueError("Endpoint must be a WebSocket URL (ws:// or wss://)")

    @property
    def endpoint(self) -> str:
        """Get the configured WebSocket endpoint."""
        return self._endpoint

    @abstractmethod
    def handle_connect(self, event: EventT, context: LambdaContext) -> ResponseT:
        """Handle connection establishment.

        Args:
            event: Connection event data
            context: Execution context

        Returns:
            Response model containing connection result
        """

    @abstractmethod
    def handle_disconnect(self, event: EventT, context: LambdaContext) -> ResponseT:
        """Handle connection termination.

        Args:
            event: Disconnection event data
            context: Execution context

        Returns:
            Response model containing disconnection result
        """
