"""Tests for WebSocket handlers module."""

from unittest.mock import Mock, patch

from amzn_nova_act_human_intervention.executors.websocket.handlers import (
    start_hitl_flow,
    websocket_connect,
    websocket_disconnect,
)


@patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
class TestWebSocketHandlers:
    """Test cases for WebSocket handler functions."""

    @patch.dict("os.environ", {"EXECUTOR_ENDPOINT": "ws://test.example.com"})
    @patch("amzn_nova_act_human_intervention.executors.websocket.handlers.ServiceManager.get_service")
    def test_websocket_connect(self, mock_get_service: Mock) -> None:
        """Test websocket_connect handler."""
        mock_service = Mock()
        mock_response = {"statusCode": 200}
        mock_service.handle_connect.return_value = mock_response
        mock_get_service.return_value = mock_service

        event = {"requestContext": {"connectionId": "test-connection-id", "routeKey": "$connect"}}
        context = Mock()

        result = websocket_connect(event, context)

        assert result == mock_response
        # The event gets converted to APIGatewayProxyEvent, so we check the call was made
        mock_service.handle_connect.assert_called_once()
        call_args = mock_service.handle_connect.call_args[0]
        assert call_args[1] == context

    @patch.dict("os.environ", {"EXECUTOR_ENDPOINT": "ws://test.example.com"})
    @patch("amzn_nova_act_human_intervention.executors.websocket.handlers.ServiceManager.get_service")
    def test_websocket_disconnect(self, mock_get_service: Mock) -> None:
        """Test websocket_disconnect handler."""
        mock_service = Mock()
        mock_response = {"statusCode": 200}
        mock_service.handle_disconnect.return_value = mock_response
        mock_get_service.return_value = mock_service

        event = {"requestContext": {"connectionId": "test-connection-id", "routeKey": "$disconnect"}}
        context = Mock()

        result = websocket_disconnect(event, context)

        assert result == mock_response
        # The event gets converted to APIGatewayProxyEvent, so we check the call was made
        mock_service.handle_disconnect.assert_called_once()
        call_args = mock_service.handle_disconnect.call_args[0]
        assert call_args[1] == context

    @patch.dict("os.environ", {"EXECUTOR_ENDPOINT": "ws://test.example.com"})
    @patch("amzn_nova_act_human_intervention.executors.websocket.handlers.ServiceManager.get_service")
    def test_start_hitl_flow(self, mock_get_service: Mock) -> None:
        """Test start_hitl_flow handler."""
        mock_service = Mock()
        mock_response = {"statusCode": 200}
        mock_service.handle_start_hitl_flow.return_value = mock_response
        mock_get_service.return_value = mock_service

        event = {
            "requestContext": {
                "connectionId": "test-connection-id",
                "routeKey": "start-hitl-flow",
            }
        }
        context = Mock()

        result = start_hitl_flow(event, context)

        assert result == mock_response
        # The event gets converted to APIGatewayProxyEvent, so we check the call was made
        mock_service.handle_start_hitl_flow.assert_called_once()
        call_args = mock_service.handle_start_hitl_flow.call_args[0]
        assert call_args[1] == context
