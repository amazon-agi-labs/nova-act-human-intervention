"""Tests for UI Takeover SFN handlers."""

from unittest.mock import Mock, patch

from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent

from amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers import (
    UITakeoverWorkflowHandler,
    completion_handler,
    confirm_if_answered,
    spa_generator_handler,
)


@patch.dict(
    "os.environ",
    {
        "AWS_REGION": "us-west-2",
        "EXECUTIONS_TABLE": "test-executions",
        "SPA_BUCKET_NAME": "test-spa-bucket",
        "SPA_CLOUDFRONT_DOMAIN": "test-cloudfront.cloudfront.net",
        "API_BASE_URL": "https://test-api.com",
        "API_PATH_PREFIX": "/api/v1",
        "DCV_LIBRARY_BASE_URL": "https://dcv.com",
        "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]',
    },
)
@patch("amzn_nova_act_human_intervention.workflows.base_handlers.NotificationFactory")
@patch("boto3.Session")
class TestUITakeoverWorkflowHandler:
    def test_handle_spa_generator_success(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test successful SPA generation."""
        mock_s3 = Mock()
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_notification = Mock()

        mock_session.return_value.client.return_value = mock_s3
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_notification_factory.return_value = mock_notification
        mock_notification.send_spa_url_notification.return_value = {"thread_ts": "1234567890.123456"}

        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test123",
                "executionArn": "arn:aws:states:us-west-2:123456789012:execution:test",
                "workflowRunId": "wf123",
                "sessionId": "sess123",
                "actId": "act123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [],
                "executionStatus": "PENDING_HUMAN_INPUT",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "https://test.execute-api.us-west-2.amazonaws.com/prod",
                "connectionId": "conn123",
            }
        }

        handler = UITakeoverWorkflowHandler()
        event = {
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
            "message": "test message",
            "remote_browser": {"session_id": "browser123"},
        }

        result = handler.handle_spa_generator(event, Mock())

        assert isinstance(result, dict)
        assert result["event_id"] == "test123"
        assert result["notification_sent"] is True
        # Verify CloudFront URL is generated correctly
        assert result["spa_url"] == "https://test-cloudfront.cloudfront.net/test123.html"
        mock_s3.put_object.assert_called_once()

    def test_handle_confirm_if_answered_completed(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test confirm if answered with completed task."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test123",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [
                    {
                        "contact_info": {
                            "type": "email",
                            "to_email_address": "test@example.com",
                            "from_email_address": "noreply@example.com",
                        }
                    }
                ],
                "executionStatus": "COMPLETED",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverWorkflowHandler()
        event = {"event_id": "test123"}

        result = handler.handle_confirm_if_answered(event, Mock())

        assert result is True

    def test_handle_confirm_if_answered_pending(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test confirm if answered with pending task."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {"Item": {"eventId": "test123", "executionStatus": "PENDING_HUMAN_INPUT"}}

        handler = UITakeoverWorkflowHandler()
        event = {"event_id": "test123"}

        result = handler.handle_confirm_if_answered(event, Mock())

        assert result is False

    def test_handle_completion_succeeded(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test completion handler with succeeded execution."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {"Item": {"eventId": "test123"}}

        handler = UITakeoverWorkflowHandler()
        event = Mock(spec=EventBridgeEvent)
        event.detail = {"executionArn": "arn:aws:states:us-west-2:123:execution:test:test123", "status": "SUCCEEDED"}

        result = handler.handle_completion(event, Mock())

        assert isinstance(result, dict)
        assert result["status"] == "success"
        mock_table.update_item.assert_called_once()


class TestLambdaHandlers:
    def test_spa_generator_handler(self) -> None:
        """Test SPA generator Lambda handler."""
        with patch(
            "amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.UITakeoverWorkflowHandler"
        ) as mock_handler_class:
            mock_handler = Mock()
            mock_handler_class.return_value = mock_handler
            mock_handler.handle_spa_generator.return_value = {"status": "success"}

            result = spa_generator_handler({"test": "data"}, Mock())

            assert result == {"status": "success"}

    def test_confirm_if_answered_handler(self) -> None:
        """Test confirm if answered Lambda handler."""
        with patch(
            "amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.UITakeoverWorkflowHandler"
        ) as mock_handler_class:
            mock_handler = Mock()
            mock_handler_class.return_value = mock_handler
            mock_handler.handle_confirm_if_answered.return_value = True

            result = confirm_if_answered({"test": "data"}, Mock())

            assert result is True

    def test_completion_handler(self) -> None:
        """Test completion Lambda handler."""
        with patch(
            "amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.UITakeoverWorkflowHandler"
        ) as mock_handler_class:
            mock_handler = Mock()
            mock_handler_class.return_value = mock_handler
            mock_handler.handle_completion.return_value = {"status": "completed"}

            event = Mock(spec=EventBridgeEvent)
            result = completion_handler(event, Mock())

            assert result == {"status": "completed"}


@patch.dict(
    "os.environ",
    {
        "AWS_REGION": "us-west-2",
        "EXECUTIONS_TABLE": "test-executions",
        "SPA_BUCKET_NAME": "test-spa-bucket",
        "SPA_CLOUDFRONT_DOMAIN": "test-cloudfront.cloudfront.net",
        "API_BASE_URL": "https://test-api.com",
        "API_PATH_PREFIX": "/api/v1",
        "DCV_LIBRARY_BASE_URL": "https://dcv.com",
        "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]',
    },
)
@patch("amzn_nova_act_human_intervention.workflows.base_handlers.NotificationFactory")
@patch("boto3.Session")
class TestUITakeoverAdditionalCoverage:
    """Additional tests to reach 95%+ coverage."""

    def test_handle_spa_generator_wrong_input_type(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test SPA generator with ApprovalStepFunctionInput instead of UITakeover."""
        handler = UITakeoverWorkflowHandler()
        event = {
            "event_id": "test123",
            "type": "Approval",  # Wrong type
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
            "query": "Approve?",
            "options": [
                {"label": "Yes", "action": "APPROVE"},
                {"label": "No", "action": "DENY"},
            ],
            "most_recent_screenshot": "data:image/png;base64,abc",
        }

        try:
            handler.handle_spa_generator(event, Mock())
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "handle_spa_generator only supports UITakeoverStepFunctionInput" in str(e)

    def test_handle_spa_generator_with_websocket_notification(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test SPA generator sends WebSocket notification when connectionId exists."""
        mock_s3 = Mock()
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_notification = Mock()

        mock_session.return_value.client.return_value = mock_s3
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_notification_factory.return_value = mock_notification
        mock_notification.send_spa_url_notification.return_value = {"thread_ts": "1234567890.123456"}

        # Mock S3 put_object to return success
        mock_s3.put_object.return_value = {}

        # Provide complete ExecutionItem fields for ExecutionItem(**response["Item"])
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test123",
                "workflowRunId": "wf123",
                "sessionId": "sess123",
                "actId": "act123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [
                    {
                        "contact_info": {
                            "type": "email",
                            "to_email_address": "test@example.com",
                            "from_email_address": "noreply@example.com",
                        }
                    }
                ],
                "executionStatus": "IN_PROGRESS",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "connectionId": "conn123",
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }
        # Mock successful update_item response
        mock_table.update_item.return_value = {}

        with patch(
            "amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.send_websocket_message"
        ) as mock_ws:
            mock_ws.return_value = True  # Mock successful WebSocket send
            handler = UITakeoverWorkflowHandler()
            event = {
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
                "message": "test message",
                "remote_browser": {"session_id": "browser123"},
            }

            result = handler.handle_spa_generator(event, Mock())

            assert isinstance(result, dict)
            assert result["event_id"] == "test123"
            # Verify put_object was called
            mock_s3.put_object.assert_called_once()
            # Verify get_item was called
            mock_table.get_item.assert_called_once()
            # Verify update_item was called
            mock_table.update_item.assert_called_once()
            # Verify WebSocket message was sent
            mock_ws.assert_called_once()
            assert mock_ws.call_args[1]["connection_id"] == "conn123"
            assert mock_ws.call_args[1]["message"]["type"] == "workflow_started"

    def test_handle_confirm_if_answered_missing_event_id(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test confirm if answered with missing event_id."""
        handler = UITakeoverWorkflowHandler()
        event: dict[str, str] = {}  # No event_id

        result = handler.handle_confirm_if_answered(event, Mock())

        assert result is False

    def test_handle_confirm_if_answered_item_not_found(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test confirm if answered when execution item not found (TTL expired)."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No Item

        handler = UITakeoverWorkflowHandler()
        event = {"event_id": "test123"}

        result = handler.handle_confirm_if_answered(event, Mock())

        # Should return True when item not found (TTL expired) to stop polling
        assert result is True

    def test_handle_confirm_if_answered_exception(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test confirm if answered with exception."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("Database error")

        handler = UITakeoverWorkflowHandler()
        event = {"event_id": "test123"}

        result = handler.handle_confirm_if_answered(event, Mock())

        assert result is False

    def test_handle_completion_invalid_event(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test completion handler with invalid event."""
        handler = UITakeoverWorkflowHandler()
        event = Mock(spec=EventBridgeEvent)
        event.detail = None  # Invalid

        result = handler.handle_completion(event, Mock())

        assert isinstance(result, dict)
        assert result["error"] == "Invalid event"

    def test_handle_completion_missing_fields(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test completion handler with missing required fields."""
        handler = UITakeoverWorkflowHandler()
        event = Mock(spec=EventBridgeEvent)
        event.detail = {"executionArn": "arn:test"}  # Missing status

        result = handler.handle_completion(event, Mock())

        assert isinstance(result, dict)
        assert result["error"] == "Missing required fields"

    def test_handle_completion_execution_not_found(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test completion handler when execution not found."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No Item

        handler = UITakeoverWorkflowHandler()
        event = Mock(spec=EventBridgeEvent)
        event.detail = {"executionArn": "arn:aws:states:us-west-2:123:execution:test:test123", "status": "SUCCEEDED"}

        result = handler.handle_completion(event, Mock())

        assert isinstance(result, dict)
        assert result["status"] == "execution_not_found"

    def test_handle_completion_with_websocket_notification(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test completion handler sends WebSocket notification when connectionId exists."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test123",
                "workflowRunId": "wf123",
                "sessionId": "sess123",
                "actId": "act123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [
                    {
                        "contact_info": {
                            "type": "email",
                            "to_email_address": "test@example.com",
                            "from_email_address": "noreply@example.com",
                        }
                    }
                ],
                "executionStatus": "COMPLETED",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "connectionId": "conn123",
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }
        # Mock successful update_item response
        mock_table.update_item.return_value = {}

        # Patch send_websocket_message in base_handlers (where handle_completion is defined)
        with patch("amzn_nova_act_human_intervention.workflows.base_handlers.send_websocket_message") as mock_ws:
            mock_ws.return_value = True  # Mock successful WebSocket send
            handler = UITakeoverWorkflowHandler()
            event = Mock(spec=EventBridgeEvent)
            event.detail = {
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test123",
                "status": "SUCCEEDED",
            }

            result = handler.handle_completion(event, Mock())

            assert isinstance(result, dict)
            assert result["status"] == "success"
            # Verify WebSocket message was sent
            mock_ws.assert_called_once()
            call_args = mock_ws.call_args
            assert call_args[1]["connection_id"] == "conn123"
            assert call_args[1]["message"]["type"] == "workflow_completed"

    def test_handle_completion_exception(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test completion handler with exception."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_session.return_value.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("Database error")

        handler = UITakeoverWorkflowHandler()
        event = Mock(spec=EventBridgeEvent)
        event.detail = {"executionArn": "arn:aws:states:us-west-2:123:execution:test:test123", "status": "SUCCEEDED"}

        result = handler.handle_completion(event, Mock())

        assert isinstance(result, dict)
        assert result["error"] == "Internal server error"


@patch("amzn_nova_act_human_intervention.workflows.base_handlers.NotificationFactory")
@patch("boto3.Session")
class TestMissingEnvironmentVariables:
    """Test missing environment variable scenarios."""

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2", "API_PATH_PREFIX": "/api/v1"}, clear=True)
    def test_handle_spa_generator_missing_api_base_url(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test SPA generator with missing API_BASE_URL."""
        handler = UITakeoverWorkflowHandler()
        event = {
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
            "message": "test message",
            "remote_browser": {"session_id": "browser123"},
        }

        try:
            handler.handle_spa_generator(event, Mock())
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "API_BASE_URL environment variable not set" in str(e)

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2", "API_BASE_URL": "https://test.com"}, clear=True)
    def test_handle_spa_generator_missing_api_path_prefix(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test SPA generator with missing API_PATH_PREFIX."""
        handler = UITakeoverWorkflowHandler()
        event = {
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
            "message": "test message",
            "remote_browser": {"session_id": "browser123"},
        }

        try:
            handler.handle_spa_generator(event, Mock())
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "API_PATH_PREFIX environment variable not set" in str(e)

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"}, clear=True)
    def test_generate_presigned_url_missing_cloudfront_domain(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test generate presigned URL with missing SPA_CLOUDFRONT_DOMAIN."""
        handler = UITakeoverWorkflowHandler()

        try:
            handler._generate_presigned_url_for_spa("test123", 3600)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "SPA_CLOUDFRONT_DOMAIN environment variable not set" in str(e)

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"}, clear=True)
    def test_write_spa_to_s3_missing_spa_bucket(self, mock_session: Mock, mock_notification_factory: Mock) -> None:
        """Test write SPA to S3 with missing SPA_BUCKET_NAME."""
        handler = UITakeoverWorkflowHandler()

        try:
            handler._write_spa_to_s3("test123", "<html></html>")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "SPA_BUCKET_NAME environment variable not set" in str(e)

    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": "us-west-2",
            "API_BASE_URL": "https://test.com",
            "API_PATH_PREFIX": "/api",
            "SPA_CLOUDFRONT_DOMAIN": "cloudfront.net",
        },
        clear=True,
    )
    def test_handle_spa_generator_missing_dcv_library_base_url(
        self, mock_session: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test SPA generator with missing DCV_LIBRARY_BASE_URL."""
        handler = UITakeoverWorkflowHandler()
        event = {
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
            "message": "test message",
            "remote_browser": {"session_id": "browser123"},
        }

        try:
            handler.handle_spa_generator(event, Mock())
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "DCV_LIBRARY_BASE_URL environment variable not set" in str(e)
