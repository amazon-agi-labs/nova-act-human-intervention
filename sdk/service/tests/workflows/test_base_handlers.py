"""Tests for base handlers module."""

from abc import ABC
from unittest.mock import Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import GenericDict, JSONType
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent, EventBridgeEvent
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.workflows.base_handlers import BaseApiHandler, BaseWorkflowHandler


class ConcreteWorkflowHandler(BaseWorkflowHandler):
    """Concrete implementation for testing BaseWorkflowHandler."""

    def handle_spa_generator(self, event: GenericDict, context: LambdaContext) -> JSONType:
        return {"status": "spa_generated"}


class ConcreteApiHandler(BaseApiHandler):
    """Concrete implementation for testing BaseApiHandler."""

    def get_browser_session_info(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        return {"session_info": {}}

    def complete_task_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        return {"status": "task_completed"}

    def task_status_handler(self, event: APIGatewayProxyEvent, context: LambdaContext) -> JSONType:
        return {"status": "pending"}


class TestBaseWorkflowHandler:
    """Test cases for BaseWorkflowHandler abstract class."""

    def test_is_abstract_class(self) -> None:
        """Test that BaseWorkflowHandler is an abstract class."""
        assert issubclass(BaseWorkflowHandler, ABC)

    def test_cannot_instantiate_directly(self) -> None:
        """Test that BaseWorkflowHandler cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseWorkflowHandler()  # type: ignore

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]', "EXECUTIONS_TABLE": "test-table"},
    )
    def test_concrete_implementation(self) -> None:
        """Test concrete implementation of BaseWorkflowHandler."""
        with patch("boto3.Session") as mock_session:
            # Mock DynamoDB table and response
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-event-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-event-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [
                        {"contact_info": {"type": "email", "email_address": "test@example.com"}}
                    ],
                    "executionStatus": "COMPLETED",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()

            # Test SPA generator
            event = {"test": "data"}
            context = Mock(spec=LambdaContext)
            spa_result = handler.handle_spa_generator(event, context)
            assert spa_result == {"status": "spa_generated"}

            # Test confirm if answered with proper event_id
            event_with_id = {"event_id": "test-event-id"}
            confirm_result = handler.handle_confirm_if_answered(event_with_id, context)
            assert confirm_result is True

            # Test completion with properly mocked EventBridge event
            eventbridge_event = Mock(spec=EventBridgeEvent)
            eventbridge_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test-state-machine:test-execution",
                "status": "SUCCEEDED",
            }

            with patch("amzn_nova_act_human_intervention.workflows.base_handlers.send_websocket_message"):
                completion_result = handler.handle_completion(eventbridge_event, context)
                assert isinstance(completion_result, dict)
                assert completion_result["status"] == "success"

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_confirm_if_answered_missing_event_id(self) -> None:
        """Test handle_confirm_if_answered with missing event_id."""
        with patch("boto3.Session"):
            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            # Test missing event_id
            result = handler.handle_confirm_if_answered({}, context)
            assert result is False

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_confirm_if_answered_item_not_found(self) -> None:
        """Test handle_confirm_if_answered when DynamoDB item not found (TTL expired)."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {}  # No Item key
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            result = handler.handle_confirm_if_answered({"event_id": "test-id"}, context)
            # Should return True when item not found (TTL expired) to stop polling
            assert result is True

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_confirm_if_answered_failed_status(self) -> None:
        """Test handle_confirm_if_answered with FAILED status."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-event-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-event-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "FAILED",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            result = handler.handle_confirm_if_answered({"event_id": "test-event-id"}, context)
            # FAILED status should be treated as answered (stop polling)
            assert result is True

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_confirm_if_answered_terminated_status(self) -> None:
        """Test handle_confirm_if_answered with TERMINATED status."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-event-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-event-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "TERMINATED",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            result = handler.handle_confirm_if_answered({"event_id": "test-event-id"}, context)
            # TERMINATED status should be treated as answered (stop polling)
            assert result is True

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_confirm_if_answered_pending_status(self) -> None:
        """Test handle_confirm_if_answered with PENDING_HUMAN_INPUT status."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-event-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-event-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "PENDING_HUMAN_INPUT",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            result = handler.handle_confirm_if_answered({"event_id": "test-event-id"}, context)
            # PENDING_HUMAN_INPUT status should be treated as not answered (continue polling)
            assert result is False

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_confirm_if_answered_exception(self) -> None:
        """Test handle_confirm_if_answered with exception."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.side_effect = Exception("DynamoDB error")
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            result = handler.handle_confirm_if_answered({"event_id": "test-id"}, context)
            assert result is False

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_completion_invalid_event(self) -> None:
        """Test handle_completion with invalid event."""
        with patch("boto3.Session"):
            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            # Test None event
            result = handler.handle_completion(None, context)  # type: ignore[arg-type]
            assert result == {"error": "Invalid event"}

            # Test event without detail
            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = None
            result = handler.handle_completion(mock_event, context)
            assert result == {"error": "Invalid event"}

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_completion_missing_fields(self) -> None:
        """Test handle_completion with missing required fields."""
        with patch("boto3.Session"):
            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            # Test missing executionArn
            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {"status": "SUCCEEDED"}
            result = handler.handle_completion(mock_event, context)
            assert result == {"error": "Missing required fields"}

            # Test missing status
            mock_event.detail = {"executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id"}
            result = handler.handle_completion(mock_event, context)
            assert result == {"error": "Missing required fields"}

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_completion_execution_not_found(self) -> None:
        """Test handle_completion when execution not found in DynamoDB."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {}  # No Item key
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                "status": "SUCCEEDED",
            }

            result = handler.handle_completion(mock_event, context)
            assert isinstance(result, dict)
            assert result["status"] == "execution_not_found"
            assert "executionArn" in result

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    @patch("time.time", return_value=1234567890)
    def test_handle_completion_failed_status_timeout(self, mock_time: Mock) -> None:
        """Test handle_completion with TIMED_OUT status."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "PENDING",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                "status": "TIMED_OUT",
            }

            with patch("amzn_nova_act_human_intervention.workflows.base_handlers.send_websocket_message"):
                result = handler.handle_completion(mock_event, context)
                assert isinstance(result, dict)
                assert result["status"] == "success"
                assert result["executionStatus"] == "FAILED"

                # Verify update_item was called with error details
                mock_table.update_item.assert_called_once()
                call_args = mock_table.update_item.call_args
                assert ":error_details" in call_args[1]["ExpressionAttributeValues"]

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    @patch("time.time", return_value=1234567890)
    def test_handle_completion_failed_status_notification_failed(self, mock_time: Mock) -> None:
        """Test handle_completion with notification failure."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "PENDING",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                "status": "FAILED",
                "cause": "NotificationDeliveryError: Notification delivery failed for channels: EMAIL",
            }

            with patch("amzn_nova_act_human_intervention.workflows.base_handlers.send_websocket_message"):
                result = handler.handle_completion(mock_event, context)
                assert isinstance(result, dict)
                assert result["status"] == "success"
                assert result["executionStatus"] == "FAILED"

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    @patch("time.time", return_value=1234567890)
    def test_handle_completion_failed_status_generic(self, mock_time: Mock) -> None:
        """Test handle_completion with generic FAILED status."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "PENDING",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                "status": "FAILED",
                "cause": "Some other error",
            }

            with patch("amzn_nova_act_human_intervention.workflows.base_handlers.send_websocket_message"):
                result = handler.handle_completion(mock_event, context)
                assert isinstance(result, dict)
                assert result["status"] == "success"
                assert result["executionStatus"] == "FAILED"

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_completion_websocket_failure(self) -> None:
        """Test handle_completion when WebSocket message fails."""
        with patch("boto3.Session") as mock_session:
            mock_table = Mock()
            mock_table.get_item.return_value = {
                "Item": {
                    "eventId": "test-id",
                    "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                    "workflowRunId": "test-workflow-run-id",
                    "sessionId": "test-session-id",
                    "actId": "test-act-id",
                    "interventionType": "UITakeover",
                    "timeout": 3600,
                    "notificationRecipients": [],
                    "executionStatus": "COMPLETED",
                    "createdAt": 1234567890,
                    "updatedAt": 1234567890,
                    "ttl": 1234567890,
                    "connectionId": "test-connection",
                    "executionEndpoint": "test-endpoint",
                }
            }
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                "status": "SUCCEEDED",
            }

            with patch(
                "amzn_nova_act_human_intervention.workflows.base_handlers.send_websocket_message",
                side_effect=Exception("WebSocket error"),
            ):
                result = handler.handle_completion(mock_event, context)
                assert isinstance(result, dict)
                assert result["status"] == "success"  # Should still succeed despite WebSocket failure

    @patch.dict(
        "os.environ",
        {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
    )
    def test_handle_completion_exception(self) -> None:
        """Test handle_completion with general exception."""
        with patch("boto3.Session") as mock_session:
            # Mock the session to raise exception during initialization
            mock_session.side_effect = Exception("General error")

            # This should fail during handler initialization
            with pytest.raises(Exception, match="General error"):
                ConcreteWorkflowHandler()

            # Test exception during handle_completion execution
            mock_session.side_effect = None  # Reset side effect
            mock_table = Mock()
            mock_table.get_item.side_effect = Exception("DynamoDB error")
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_session.return_value.resource.return_value = mock_dynamodb

            handler = ConcreteWorkflowHandler()
            context = Mock(spec=LambdaContext)

            mock_event = Mock(spec=EventBridgeEvent)
            mock_event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test:test-id",
                "status": "SUCCEEDED",
            }

            result = handler.handle_completion(mock_event, context)
            assert isinstance(result, dict)
            assert "error" in result
            assert result["error"] == "Internal server error"

    def test_abstract_methods_exist(self) -> None:
        """Test that all required abstract methods exist."""
        abstract_methods = BaseWorkflowHandler.__abstractmethods__
        expected_methods = {
            "handle_spa_generator",
        }
        assert abstract_methods == expected_methods


class TestBaseApiHandler:
    """Test cases for BaseApiHandler abstract class."""

    def test_is_abstract_class(self) -> None:
        """Test that BaseApiHandler is an abstract class."""
        assert issubclass(BaseApiHandler, ABC)

    def test_cannot_instantiate_directly(self) -> None:
        """Test that BaseApiHandler cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseApiHandler()  # type: ignore

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    def test_concrete_implementation(self) -> None:
        """Test concrete implementation of BaseApiHandler."""
        handler = ConcreteApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        context = Mock(spec=LambdaContext)

        # Test all abstract methods are implemented
        session_result = handler.get_browser_session_info(event, context)
        complete_result = handler.complete_task_handler(event, context)
        status_result = handler.task_status_handler(event, context)

        assert session_result == {"session_info": {}}
        assert complete_result == {"status": "task_completed"}
        assert status_result == {"status": "pending"}

    def test_abstract_methods_exist(self) -> None:
        """Test that all required abstract methods exist."""
        abstract_methods = BaseApiHandler.__abstractmethods__
        expected_methods = {
            "get_browser_session_info",
            "complete_task_handler",
            "task_status_handler",
        }
        assert abstract_methods == expected_methods
