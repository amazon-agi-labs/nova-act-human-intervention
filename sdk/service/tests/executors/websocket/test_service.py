"""Tests for WebSocket service."""

import json
from http import HTTPStatus
from unittest.mock import Mock, patch

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from amzn_nova_act_human_intervention.executors.websocket.service import WebSocketService


@patch.dict(
    "os.environ",
    {
        "CONNECTIONS_TABLE": "test-connections",
        "EXECUTIONS_TABLE": "test-executions",
        "STATE_MACHINE_ARNS": '{"UITakeover": "arn:aws:states:us-west-2:123:stateMachine:test"}',
    },
)
@patch("amzn_nova_act_human_intervention.executors.websocket.service.boto3")
class TestWebSocketService:
    def test_handle_connect_success(self, mock_boto3: Mock) -> None:
        """Test successful connection."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"

        result = service.handle_connect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == 200
        mock_table.put_item.assert_called_once()

    def test_handle_connect_missing_connection_id(self, mock_boto3: Mock) -> None:
        """Test connection with missing ID."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = None

        result = service.handle_connect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_disconnect_success(self, mock_boto3: Mock) -> None:
        """Test successful disconnection."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"

        result = service.handle_disconnect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == 200
        mock_table.delete_item.assert_called_once_with(Key={"connectionId": "conn123"})

    @patch("time.time", return_value=1000)
    def test_handle_start_hitl_flow_success(self, mock_time: Mock, mock_boto3: Mock) -> None:
        """Test successful HITL flow start."""
        mock_executions_table = Mock()
        mock_stepfunctions = Mock()
        mock_stepfunctions.start_execution.return_value = {"executionArn": "arn:test"}

        mock_boto3.resource().Table.side_effect = [Mock(), mock_executions_table]
        mock_boto3.client.return_value = mock_stepfunctions

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"
        event.body = json.dumps(
            {
                "action": "start_intervention",
                "input": {
                    "event_id": "test123",
                    "type": "UITakeover",
                    "timeout": 3600,
                    "workflow_run_id": "wf123",
                    "session_id": "sess123",
                    "act_id": "act123",
                    "notification_recipients": [
                        {
                            "contact_info": {
                                "type": "email",
                                "to_email_address": "test@example.com",
                                "from_email_address": "noreply@example.com",
                            }
                        }
                    ],
                    "message": "test",
                    "remote_browser": {"session_id": "browser123"},
                },
            }
        )

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        mock_stepfunctions.start_execution.assert_called_once()
        mock_executions_table.put_item.assert_called_once()

    def test_handle_start_hitl_flow_missing_body(self, mock_boto3: Mock) -> None:
        """Test HITL flow with missing body."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"
        event.body = None

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_init_invalid_endpoint(self, mock_boto3: Mock) -> None:
        """Test initialization with invalid endpoint."""
        with pytest.raises(ValueError):
            WebSocketService("http://invalid.com")

    def test_handle_connect_missing_request_context(self, mock_boto3: Mock) -> None:
        """Test connection with missing request context."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context = None

        result = service.handle_connect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_connect_invalid_ttl(self, mock_boto3: Mock) -> None:
        """Test connection with invalid TTL."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"

        result = service.handle_connect(event, Mock(), ttl_seconds=0)

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_connect_negative_ttl(self, mock_boto3: Mock) -> None:
        """Test connection with negative TTL."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"

        result = service.handle_connect(event, Mock(), ttl_seconds=-100)

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_connect_dynamodb_exception(self, mock_boto3: Mock) -> None:
        """Test connection with DynamoDB exception."""
        mock_table = Mock()
        mock_table.put_item.side_effect = Exception("DynamoDB error")
        mock_boto3.resource().Table.return_value = mock_table

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"

        result = service.handle_connect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_handle_disconnect_missing_request_context(self, mock_boto3: Mock) -> None:
        """Test disconnection with missing request context."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context = None

        result = service.handle_disconnect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_disconnect_missing_connection_id(self, mock_boto3: Mock) -> None:
        """Test disconnection with missing connection ID."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = None

        result = service.handle_disconnect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_disconnect_dynamodb_exception(self, mock_boto3: Mock) -> None:
        """Test disconnection with DynamoDB exception."""
        mock_table = Mock()
        mock_table.delete_item.side_effect = Exception("DynamoDB error")
        mock_boto3.resource().Table.return_value = mock_table

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"

        result = service.handle_disconnect(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_handle_start_hitl_flow_missing_request_context(self, mock_boto3: Mock) -> None:
        """Test HITL flow with missing request context."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context = None
        event.body = json.dumps({"action": "start_intervention", "input": {}})

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_start_hitl_flow_missing_connection_id(self, mock_boto3: Mock) -> None:
        """Test HITL flow with missing connection ID."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = None
        event.body = json.dumps({"action": "start_intervention", "input": {}})

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    @patch.dict(
        "os.environ",
        {
            "CONNECTIONS_TABLE": "test-connections",
            "EXECUTIONS_TABLE": "test-executions",
            "STATE_MACHINE_ARNS": '{"Approval": "arn:aws:states:us-west-2:123:stateMachine:approval"}',
        },
    )
    @patch("time.time", return_value=1000)
    def test_handle_start_hitl_flow_state_machine_not_configured(self, mock_time: Mock, mock_boto3: Mock) -> None:
        """Test HITL flow with state machine ARN not configured."""
        mock_boto3.resource().Table.return_value = Mock()
        mock_boto3.client.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"
        event.body = json.dumps(
            {
                "action": "start_intervention",
                "input": {
                    "event_id": "test123",
                    "type": "UITakeover",
                    "timeout": 3600,
                    "workflow_run_id": "wf123",
                    "session_id": "sess123",
                    "act_id": "act123",
                    "notification_recipients": [
                        {
                            "contact_info": {
                                "type": "email",
                                "to_email_address": "test@example.com",
                                "from_email_address": "noreply@example.com",
                            }
                        }
                    ],
                    "message": "test",
                    "remote_browser": {"session_id": "browser123"},
                },
            }
        )

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    @patch("time.time", return_value=1000)
    def test_handle_start_hitl_flow_dynamodb_failure_compensation(self, mock_time: Mock, mock_boto3: Mock) -> None:
        """Test HITL flow with DynamoDB failure triggering compensating transaction."""
        mock_executions_table = Mock()
        mock_executions_table.put_item.side_effect = Exception("DynamoDB write failed")
        mock_stepfunctions = Mock()
        mock_stepfunctions.start_execution.return_value = {"executionArn": "arn:test"}

        mock_boto3.resource().Table.side_effect = [Mock(), mock_executions_table]
        mock_boto3.client.return_value = mock_stepfunctions

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"
        event.body = json.dumps(
            {
                "action": "start_intervention",
                "input": {
                    "event_id": "test123",
                    "type": "UITakeover",
                    "timeout": 3600,
                    "workflow_run_id": "wf123",
                    "session_id": "sess123",
                    "act_id": "act123",
                    "notification_recipients": [
                        {
                            "contact_info": {
                                "type": "email",
                                "to_email_address": "test@example.com",
                                "from_email_address": "noreply@example.com",
                            }
                        }
                    ],
                    "message": "test",
                    "remote_browser": {"session_id": "browser123"},
                },
            }
        )

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR
        mock_stepfunctions.stop_execution.assert_called_once_with(
            executionArn="arn:test", error="DatabaseWriteFailure", cause="DynamoDB write failed"
        )

    @patch("time.time", return_value=1000)
    def test_handle_start_hitl_flow_compensation_stop_fails(self, mock_time: Mock, mock_boto3: Mock) -> None:
        """Test HITL flow where both DynamoDB and stop_execution fail."""
        mock_executions_table = Mock()
        mock_executions_table.put_item.side_effect = Exception("DynamoDB write failed")
        mock_stepfunctions = Mock()
        mock_stepfunctions.start_execution.return_value = {"executionArn": "arn:test"}
        mock_stepfunctions.stop_execution.side_effect = Exception("Stop execution failed")

        mock_boto3.resource().Table.side_effect = [Mock(), mock_executions_table]
        mock_boto3.client.return_value = mock_stepfunctions

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"
        event.body = json.dumps(
            {
                "action": "start_intervention",
                "input": {
                    "event_id": "test123",
                    "type": "UITakeover",
                    "timeout": 3600,
                    "workflow_run_id": "wf123",
                    "session_id": "sess123",
                    "act_id": "act123",
                    "notification_recipients": [
                        {
                            "contact_info": {
                                "type": "email",
                                "to_email_address": "test@example.com",
                                "from_email_address": "noreply@example.com",
                            }
                        }
                    ],
                    "message": "test",
                    "remote_browser": {"session_id": "browser123"},
                },
            }
        )

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR
        mock_stepfunctions.stop_execution.assert_called_once()

    @patch("time.time", return_value=1000)
    def test_handle_start_hitl_flow_invalid_payload(self, mock_time: Mock, mock_boto3: Mock) -> None:
        """Test HITL flow with invalid payload."""
        mock_boto3.resource().Table.return_value = Mock()
        mock_boto3.client.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "conn123"
        event.body = json.dumps({"invalid": "payload"})

        result = service.handle_start_hitl_flow(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_handle_connection_refresh_success(self, mock_boto3: Mock) -> None:
        """Test successful connection refresh."""
        mock_executions_table = Mock()
        mock_boto3.resource().Table.side_effect = [Mock(), mock_executions_table]

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "new_conn456"
        event.body = json.dumps({"eventId": "event123"})

        result = service.handle_connection_refresh(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == 200
        mock_executions_table.update_item.assert_called_once_with(
            Key={"eventId": "event123"},
            UpdateExpression="SET connectionId = :new_connection_id",
            ExpressionAttributeValues={":new_connection_id": "new_conn456"},
            ConditionExpression="attribute_exists(eventId)",
        )

    def test_handle_connection_refresh_missing_event_id(self, mock_boto3: Mock) -> None:
        """Test connection refresh with missing event ID."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "new_conn456"
        event.body = json.dumps({})

        result = service.handle_connection_refresh(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_connection_refresh_missing_connection_id(self, mock_boto3: Mock) -> None:
        """Test connection refresh with missing connection ID."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = None
        event.body = json.dumps({"eventId": "event123"})

        result = service.handle_connection_refresh(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_connection_refresh_execution_not_found(self, mock_boto3: Mock) -> None:
        """Test connection refresh when execution doesn't exist."""
        from botocore.exceptions import ClientError

        mock_executions_table = Mock()
        mock_executions_table.update_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
        )

        # Setup the mock to return the proper exception type
        mock_dynamodb = Mock()
        mock_dynamodb.meta.client.exceptions.ConditionalCheckFailedException = ClientError
        mock_boto3.resource.return_value = mock_dynamodb
        mock_boto3.resource().Table.side_effect = [Mock(), mock_executions_table]

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "new_conn456"
        event.body = json.dumps({"eventId": "nonexistent"})

        result = service.handle_connection_refresh(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.NOT_FOUND

    def test_handle_connection_refresh_invalid_json(self, mock_boto3: Mock) -> None:
        """Test connection refresh with invalid JSON."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "new_conn456"
        event.body = "invalid json"

        result = service.handle_connection_refresh(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_handle_connection_refresh_missing_body(self, mock_boto3: Mock) -> None:
        """Test connection refresh with missing body."""
        mock_boto3.resource().Table.return_value = Mock()

        service = WebSocketService("ws://test.com")
        event = Mock(spec=APIGatewayProxyEvent)
        event.request_context.connection_id = "new_conn456"
        event.body = None

        result = service.handle_connection_refresh(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST
