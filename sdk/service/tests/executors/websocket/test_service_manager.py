"""Tests for ServiceManager class."""

from unittest.mock import Mock, patch

import pytest

from amzn_nova_act_human_intervention.executors.websocket.handlers import ServiceManager
from amzn_nova_act_human_intervention.executors.websocket.service import WebSocketService


@patch.dict("os.environ", {"AWS_DEFAULT_REGION": "us-west-2"})
class TestServiceManager:
    """Test cases for ServiceManager class."""

    def setup_method(self) -> None:
        """Reset ServiceManager state before each test."""
        ServiceManager._instance = None

    @patch.dict(
        "os.environ",
        {
            "EXECUTOR_ENDPOINT": "ws://test.example.com",
            "CONNECTIONS_TABLE": "test-table",
            "EXECUTIONS_TABLE": "test-executions-table",
            "STATE_MACHINE_ARNS": '{"UITakeover": "arn:aws:states:us-west-2:123456789012:stateMachine:UITakeover"}',
        },
    )
    @patch("boto3.resource")
    def test_get_service_creates_instance(self, mock_boto3_resource: Mock) -> None:
        """Test that get_service creates a new instance when none exists."""
        mock_dynamodb = Mock()
        mock_boto3_resource.return_value = mock_dynamodb

        service = ServiceManager.get_service()

        assert isinstance(service, WebSocketService)
        assert service.endpoint == "ws://test.example.com"
        assert ServiceManager._instance is service

    @patch.dict(
        "os.environ",
        {
            "EXECUTOR_ENDPOINT": "ws://test.example.com",
            "CONNECTIONS_TABLE": "test-table",
            "EXECUTIONS_TABLE": "test-executions-table",
            "STATE_MACHINE_ARNS": '{"UITakeover": "arn:aws:states:us-west-2:123456789012:stateMachine:UITakeover"}',
        },
    )
    @patch("boto3.resource")
    def test_get_service_returns_existing_instance(self, mock_boto3_resource: Mock) -> None:
        """Test that get_service returns existing instance on subsequent calls."""
        mock_dynamodb = Mock()
        mock_boto3_resource.return_value = mock_dynamodb

        # First call creates instance
        service1 = ServiceManager.get_service()
        # Second call should return same instance
        service2 = ServiceManager.get_service()

        assert service1 is service2
        # boto3.resource should only be called once during first instantiation
        mock_boto3_resource.assert_called_once()

    @patch.dict("os.environ", {"EXECUTOR_ENDPOINT": ""})
    def test_get_service_missing_endpoint(self) -> None:
        """Test that get_service raises assertion error when endpoint is missing."""
        with pytest.raises(EnvironmentError, match="EXECUTOR_ENDPOINT environment variable must be set"):
            ServiceManager.get_service()

    @patch.dict("os.environ", {})
    def test_get_service_no_endpoint_env_var(self) -> None:
        """Test that get_service raises assertion error when endpoint env var is not set."""
        with pytest.raises(EnvironmentError, match="EXECUTOR_ENDPOINT environment variable must be set"):
            ServiceManager.get_service()
