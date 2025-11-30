"""Tests for executors factory module."""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from amzn_nova_act_human_intervention.executors.base import BaseInterventionExecutor, ExecutorType
from amzn_nova_act_human_intervention.executors.factory import ExecutorFactory
from amzn_nova_act_human_intervention.executors.websocket.service import WebSocketService


class MockExecutor(BaseInterventionExecutor):
    """Mock executor for testing."""

    def handle_connect(self, event: Any, context: Any) -> Mock:
        return Mock()

    def handle_disconnect(self, event: Any, context: Any) -> Mock:
        return Mock()


@patch.dict(
    "os.environ",
    {
        "AWS_DEFAULT_REGION": "us-west-2",
        "EXECUTOR_ENDPOINT": "ws://test.example.com",
        "CONNECTIONS_TABLE": "test-table",
        "EXECUTIONS_TABLE": "test-executions-table",
        "STATE_MACHINE_ARNS": '{"UITakeover": "arn:aws:states:us-west-2:123456789012:stateMachine:UITakeover"}',
    },
)
class TestExecutorFactory:
    """Test cases for ExecutorFactory class."""

    def setup_method(self) -> None:
        """Reset factory state before each test."""
        ExecutorFactory._executor_registry = {
            ExecutorType.WEBSOCKET: WebSocketService,
        }

    @patch("boto3.resource")
    def test_create_websocket_executor(self, mock_boto3_resource: Mock) -> None:
        """Test creating WebSocket executor."""
        endpoint = "ws://example.com/websocket"

        executor = ExecutorFactory.create_executor(ExecutorType.WEBSOCKET, endpoint)

        assert isinstance(executor, WebSocketService)
        assert executor.endpoint == endpoint

    def test_create_executor_unsupported_type(self) -> None:
        """Test creating executor with unsupported type."""
        # Create a mock executor type that's not registered
        mock_type = Mock()
        mock_type.name = "UNSUPPORTED"

        with pytest.raises(ValueError, match="Unsupported executor type"):
            ExecutorFactory.create_executor(mock_type, "ws://example.com")

    def test_register_executor_valid(self) -> None:
        """Test registering a valid executor class."""
        mock_type = Mock()

        ExecutorFactory.register_executor(mock_type, MockExecutor)

        assert mock_type in ExecutorFactory._executor_registry
        assert ExecutorFactory._executor_registry[mock_type] == MockExecutor

    def test_register_executor_invalid_class(self) -> None:
        """Test registering invalid executor class."""
        mock_type = Mock()

        class InvalidExecutor:
            pass

        with pytest.raises(TypeError, match="Executor class must inherit from BaseInterventionExecutor"):
            ExecutorFactory.register_executor(mock_type, InvalidExecutor)  # type: ignore

    def test_get_supported_types(self) -> None:
        """Test getting supported executor types."""
        supported_types = ExecutorFactory.get_supported_types()

        assert ExecutorType.WEBSOCKET in supported_types
        assert len(supported_types) == 1

    def test_get_supported_types_after_registration(self) -> None:
        """Test getting supported types after registering new executor."""
        mock_type = Mock()
        ExecutorFactory.register_executor(mock_type, MockExecutor)

        supported_types = ExecutorFactory.get_supported_types()

        assert ExecutorType.WEBSOCKET in supported_types
        assert mock_type in supported_types
        assert len(supported_types) == 2
