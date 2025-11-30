"""Tests for executors base module."""

from unittest.mock import Mock, patch

import pytest
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel

from amzn_nova_act_human_intervention.executors.base import BaseInterventionExecutor, ExecutorType


class MockEvent(BaseModel):
    """Mock event model for testing."""

    data: str


class MockResponse(BaseModel):
    """Mock response model for testing."""

    result: str


class ConcreteExecutor(BaseInterventionExecutor[MockEvent, MockResponse]):
    """Concrete implementation for testing."""

    def handle_connect(self, event: MockEvent, context: LambdaContext) -> MockResponse:
        return MockResponse(result="connected")

    def handle_disconnect(self, event: MockEvent, context: LambdaContext) -> MockResponse:
        return MockResponse(result="disconnected")


class TestExecutorType:
    """Test cases for ExecutorType enum."""

    def test_websocket_type(self) -> None:
        """Test WEBSOCKET executor type."""
        assert ExecutorType.WEBSOCKET.value == "websocket"


class TestBaseInterventionExecutor:
    """Test cases for BaseInterventionExecutor class."""

    @patch("amzn_nova_act_human_intervention_common.config.logging_config.LoggingConfig.get_logger")
    def test_valid_websocket_url_ws(self, mock_get_logger: Mock) -> None:
        """Test initialization with valid ws:// URL."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        executor = ConcreteExecutor("ws://example.com/websocket")

        assert executor.endpoint == "ws://example.com/websocket"
        assert executor.logger == mock_logger

    @patch("amzn_nova_act_human_intervention_common.LoggingConfig.get_logger")
    def test_valid_websocket_url_wss(self, mock_get_logger: Mock) -> None:
        """Test initialization with valid wss:// URL."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        executor = ConcreteExecutor("wss://example.com/websocket")

        assert executor.endpoint == "wss://example.com/websocket"

    def test_invalid_websocket_url_empty(self) -> None:
        """Test initialization with empty URL."""
        with pytest.raises(ValueError, match="Endpoint must be a non-empty string"):
            ConcreteExecutor("")

    def test_invalid_websocket_url_none(self) -> None:
        """Test initialization with None URL."""
        with pytest.raises(ValueError, match="Endpoint must be a non-empty string"):
            ConcreteExecutor(None)  # type: ignore

    def test_invalid_websocket_url_http(self) -> None:
        """Test initialization with HTTP URL."""
        with pytest.raises(ValueError, match="Endpoint must be a WebSocket URL"):
            ConcreteExecutor("http://example.com")

    def test_invalid_websocket_url_https(self) -> None:
        """Test initialization with HTTPS URL."""
        with pytest.raises(ValueError, match="Endpoint must be a WebSocket URL"):
            ConcreteExecutor("https://example.com")

    def test_invalid_websocket_url_invalid_protocol(self) -> None:
        """Test initialization with invalid protocol."""
        with pytest.raises(ValueError, match="Endpoint must be a WebSocket URL"):
            ConcreteExecutor("ftp://example.com")

    def test_endpoint_property(self) -> None:
        """Test endpoint property getter."""
        url = "ws://example.com/websocket"
        executor = ConcreteExecutor(url)

        assert executor.endpoint == url

    def test_handle_connect_implementation(self) -> None:
        """Test concrete implementation of handle_connect."""
        executor = ConcreteExecutor("ws://example.com")
        event = MockEvent(data="test")
        context = Mock(spec=LambdaContext)

        response = executor.handle_connect(event, context)

        assert isinstance(response, MockResponse)
        assert response.result == "connected"

    def test_handle_disconnect_implementation(self) -> None:
        """Test concrete implementation of handle_disconnect."""
        executor = ConcreteExecutor("ws://example.com")
        event = MockEvent(data="test")
        context = Mock(spec=LambdaContext)

        response = executor.handle_disconnect(event, context)

        assert isinstance(response, MockResponse)
        assert response.result == "disconnected"
