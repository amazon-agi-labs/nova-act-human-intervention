"""Tests for WebSocket utility module."""

import json
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from amzn_nova_act_human_intervention.utils.websocket import send_websocket_message


class TestSendWebSocketMessage:
    """Test cases for send_websocket_message function."""

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    def test_send_message_success_wss(self, mock_boto3: Mock) -> None:
        """Test successful message sending with wss:// endpoint."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        endpoint = "wss://abc123.execute-api.us-west-2.amazonaws.com/prod"
        connection_id = "conn-123"
        message = {"type": "workflow_started", "eventId": "event-123"}

        send_websocket_message(endpoint, connection_id, message)

        # Verify client creation with converted endpoint
        mock_boto3.client.assert_called_once_with(
            "apigatewaymanagementapi",
            endpoint_url="https://abc123.execute-api.us-west-2.amazonaws.com/prod",
            region_name="us-west-2",
        )

        # Verify post_to_connection call
        mock_client.post_to_connection.assert_called_once_with(
            ConnectionId=connection_id, Data=json.dumps(message).encode("utf-8")
        )

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    def test_send_message_success_ws(self, mock_boto3: Mock) -> None:
        """Test successful message sending with ws:// endpoint."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        endpoint = "ws://abc123.execute-api.us-west-2.amazonaws.com/prod"
        connection_id = "conn-456"
        message = {"type": "workflow_completed", "eventId": "event-456"}

        send_websocket_message(endpoint, connection_id, message)

        # Verify client creation with converted endpoint (ws:// -> http://)
        mock_boto3.client.assert_called_once_with(
            "apigatewaymanagementapi",
            endpoint_url="http://abc123.execute-api.us-west-2.amazonaws.com/prod",
            region_name="us-west-2",
        )

        # Verify post_to_connection call
        mock_client.post_to_connection.assert_called_once_with(
            ConnectionId=connection_id, Data=json.dumps(message).encode("utf-8")
        )

    @patch.dict("os.environ", {"AWS_REGION": "us-east-1"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    @patch("amzn_nova_act_human_intervention.utils.websocket.logger")
    def test_send_message_gone_exception(self, mock_logger: Mock, mock_boto3: Mock) -> None:
        """Test handling of GoneException when connection is closed."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Create GoneException
        gone_exception = ClientError(
            {"Error": {"Code": "GoneException", "Message": "Connection is gone"}}, "PostToConnection"
        )
        mock_client.exceptions.GoneException = type(gone_exception)
        mock_client.post_to_connection.side_effect = gone_exception

        endpoint = "wss://abc123.execute-api.us-east-1.amazonaws.com/prod"
        connection_id = "conn-gone"
        message = {"type": "test_message"}

        # Should not raise exception
        send_websocket_message(endpoint, connection_id, message)

        # Verify warning was logged
        mock_logger.warning.assert_called_once_with(f"WebSocket connection {connection_id} is gone")

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    @patch("amzn_nova_act_human_intervention.utils.websocket.logger")
    def test_send_message_generic_exception(self, mock_logger: Mock, mock_boto3: Mock) -> None:
        """Test handling of generic exception during message sending."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Simulate generic exception
        mock_client.post_to_connection.side_effect = Exception("Network error")

        endpoint = "wss://abc123.execute-api.us-west-2.amazonaws.com/prod"
        connection_id = "conn-error"
        message = {"type": "test_message"}

        # Should not raise exception
        send_websocket_message(endpoint, connection_id, message)

        # Verify error was logged
        mock_logger.error.assert_called()
        error_calls = mock_logger.error.call_args_list
        assert len(error_calls) >= 2
        assert f"Failed to send WebSocket message to {connection_id}" in str(error_calls[0])
        assert "Traceback:" in str(error_calls[1])

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    @patch("amzn_nova_act_human_intervention.utils.websocket.logger")
    def test_send_message_success_logging(self, mock_logger: Mock, mock_boto3: Mock) -> None:
        """Test successful message logging."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        endpoint = "wss://abc123.execute-api.us-west-2.amazonaws.com/prod"
        connection_id = "conn-log-test"
        message = {"type": "workflow_started", "eventId": "event-log"}

        send_websocket_message(endpoint, connection_id, message)

        # Verify info log
        mock_logger.info.assert_called_once_with(
            f"Sent WebSocket message to connection {connection_id}: workflow_started"
        )

    @patch.dict("os.environ", {"AWS_REGION": "eu-west-1"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    def test_send_message_with_complex_payload(self, mock_boto3: Mock) -> None:
        """Test sending message with complex nested payload."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        endpoint = "wss://xyz789.execute-api.eu-west-1.amazonaws.com/prod"
        connection_id = "conn-complex"
        message = {
            "type": "workflow_started",
            "eventId": "event-complex",
            "data": {"nested": {"field": "value"}, "list": [1, 2, 3]},
        }

        send_websocket_message(endpoint, connection_id, message)

        # Verify the message was properly JSON encoded
        call_args = mock_client.post_to_connection.call_args
        assert call_args[1]["ConnectionId"] == connection_id
        data = call_args[1]["Data"]
        decoded_message = json.loads(data.decode("utf-8"))
        assert decoded_message == message

    @patch.dict("os.environ", {}, clear=True)
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    def test_send_message_no_region_env(self, mock_boto3: Mock) -> None:
        """Test message sending without AWS_REGION environment variable."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        endpoint = "wss://abc123.execute-api.us-west-2.amazonaws.com/prod"
        connection_id = "conn-no-region"
        message = {"type": "test"}

        send_websocket_message(endpoint, connection_id, message)

        # Verify client was created with region_name=None
        mock_boto3.client.assert_called_once_with(
            "apigatewaymanagementapi",
            endpoint_url="https://abc123.execute-api.us-west-2.amazonaws.com/prod",
            region_name=None,
        )

    @patch.dict("os.environ", {"AWS_REGION": "ap-south-1"})
    @patch("amzn_nova_act_human_intervention.utils.websocket.boto3")
    def test_endpoint_conversion_multiple_protocols(self, mock_boto3: Mock) -> None:
        """Test endpoint conversion for both wss:// and ws:// protocols."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Test wss:// conversion
        endpoint_wss = "wss://test.execute-api.ap-south-1.amazonaws.com/stage"
        send_websocket_message(endpoint_wss, "conn-1", {"type": "test"})

        call_args_wss = mock_boto3.client.call_args
        assert call_args_wss[1]["endpoint_url"] == "https://test.execute-api.ap-south-1.amazonaws.com/stage"

        # Reset mock
        mock_boto3.client.reset_mock()

        # Test ws:// conversion
        endpoint_ws = "ws://test.execute-api.ap-south-1.amazonaws.com/stage"
        send_websocket_message(endpoint_ws, "conn-2", {"type": "test"})

        call_args_ws = mock_boto3.client.call_args
        assert call_args_ws[1]["endpoint_url"] == "http://test.execute-api.ap-south-1.amazonaws.com/stage"
