"""Tests for UI Takeover API handlers."""

import json
from http import HTTPStatus
from unittest.mock import Mock, patch

from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers import UITakeoverApiHandler


@patch.dict(
    "os.environ",
    {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
)
@patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.boto3")
class TestUITakeoverApiHandler:
    def test_get_browser_session_info_success(self, mock_boto3: Mock) -> None:
        """Test successful browser session info retrieval."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {
                "status": "RUNNING",
                "sessionId": "test-session",
                "streams": {"liveViewStream": {"url": "wss://test.com"}},
            }
            mock_browser_instance.generate_live_view_url.return_value = "https://presigned.com"

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            result = handler.get_browser_session_info(event, Mock())

            assert isinstance(result, dict)
            assert result["statusCode"] == HTTPStatus.OK
            body = json.loads(result["body"])  # type: ignore[arg-type]
            assert body["streams"]["liveViewStream"]["presignedUrl"] == "https://presigned.com"

    def test_get_browser_session_info_terminated(self, mock_boto3: Mock) -> None:
        """Test browser session info with terminated session raises RuntimeError and updates DynamoDB."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {"status": "TERMINATED"}

            mock_table = Mock()
            mock_boto3.resource().Table.return_value = mock_table

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            # Should raise RuntimeError to fail the Step Function execution
            try:
                handler.get_browser_session_info(event, Mock())
                assert False, "Expected RuntimeError to be raised"
            except RuntimeError as e:
                assert "Remote browser has been terminated" in str(e)

            # Verify DynamoDB was updated with error details before raising exception
            mock_table.update_item.assert_called_once()
            update_call = mock_table.update_item.call_args
            assert update_call[1]["Key"] == {"eventId": "test-token"}
            assert "errorDetails" in update_call[1]["UpdateExpression"]
            assert ":error_details" in update_call[1]["ExpressionAttributeValues"]
            error_details_dict = update_call[1]["ExpressionAttributeValues"][":error_details"]
            assert error_details_dict["code"] == "BROWSER_SESSION_TERMINATED"
            assert "browser session has been terminated" in error_details_dict["message"].lower()

    def test_complete_task_handler_success(self, mock_boto3: Mock) -> None:
        """Test successful task completion."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "PENDING_HUMAN_INPUT",  # Not yet completed
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.complete_task_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["task_completed"] is True
        mock_table.update_item.assert_called_once()

    def test_complete_task_handler_not_found(self, mock_boto3: Mock) -> None:
        """Test task completion with non-existent task."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.complete_task_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.NOT_FOUND

    def test_complete_task_handler_already_completed(self, mock_boto3: Mock) -> None:
        """Test task completion when task is already completed (replay attack prevention)."""
        from botocore.exceptions import ClientError

        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "COMPLETED",  # Already completed
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        # Mock ConditionalCheckFailedException when trying to update completed task
        mock_table.meta.client.exceptions.ConditionalCheckFailedException = ClientError
        mock_table.update_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
        )

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.complete_task_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.CONFLICT
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert "already completed" in body["error"].lower()
        assert body["currentStatus"] == "COMPLETED"
        # Verify update_item was called (and failed with condition check)
        mock_table.update_item.assert_called_once()

    def test_task_status_handler_completed(self, mock_boto3: Mock) -> None:
        """Test task status for completed task."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "COMPLETED",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["task_completed"] is True

    def test_terminate_workflow_handler_success(self, mock_boto3: Mock) -> None:
        """Test successful workflow termination."""
        mock_table = Mock()
        mock_sfn = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_boto3.client.return_value = mock_sfn
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "IN_PROGRESS",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["workflow_terminated"] is True
        mock_sfn.stop_execution.assert_called_once()

    def test_view_details_handler_success(self, mock_boto3: Mock) -> None:
        """Test successful workflow details retrieval."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "PENDING_HUMAN_INPUT",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.view_details_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["actId"] == "act-123"
        assert body["workflowRunId"] == "wf-123"

    def test_get_browser_session_info_invalid_json(self, mock_boto3: Mock) -> None:
        """Test browser session info with invalid JSON."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = "invalid json"

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_get_browser_session_info_empty_body(self, mock_boto3: Mock) -> None:
        """Test browser session info with empty body."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = None

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_get_browser_session_info_missing_token(self, mock_boto3: Mock) -> None:
        """Test browser session info with missing token."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"remote_browser": {"session_id": "test"}})

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_get_browser_session_info_missing_remote_browser(self, mock_boto3: Mock) -> None:
        """Test browser session info with missing remote_browser."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_get_browser_session_info_invalid_remote_browser_format(self, mock_boto3: Mock) -> None:
        """Test browser session info with invalid remote_browser format."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "remote_browser": "invalid"})

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_get_browser_session_info_missing_session_id(self, mock_boto3: Mock) -> None:
        """Test browser session info with missing session_id."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "remote_browser": {}})

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    @patch.dict(
        "os.environ", {"EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'}, clear=True
    )
    @patch("amzn_nova_act_human_intervention.workflows.base_handlers.NotificationFactory")
    def test_get_browser_session_info_missing_aws_region(
        self, mock_notification_factory: Mock, mock_boto3: Mock
    ) -> None:
        """Test browser session info with missing AWS_REGION."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test"}})

        try:
            handler.get_browser_session_info(event, Mock())
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "AWS_REGION" in str(e)

    def test_complete_task_handler_invalid_json(self, mock_boto3: Mock) -> None:
        """Test task completion with invalid JSON."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = "invalid json"

        result = handler.complete_task_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_complete_task_handler_missing_token(self, mock_boto3: Mock) -> None:
        """Test task completion with missing token."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({})

        result = handler.complete_task_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_complete_task_handler_exception(self, mock_boto3: Mock) -> None:
        """Test task completion with exception."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.complete_task_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_task_status_handler_invalid_json(self, mock_boto3: Mock) -> None:
        """Test task status with invalid JSON."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = "invalid json"

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_task_status_handler_missing_token(self, mock_boto3: Mock) -> None:
        """Test task status with missing token."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({})

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_task_status_handler_not_found(self, mock_boto3: Mock) -> None:
        """Test task status with non-existent task."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.NOT_FOUND

    def test_task_status_handler_terminated(self, mock_boto3: Mock) -> None:
        """Test task status for terminated task."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "TERMINATED",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["task_completed"] is True

    def test_task_status_handler_failed(self, mock_boto3: Mock) -> None:
        """Test task status for failed task includes error details."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "FAILED",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
                "errorDetails": {
                    "code": "BROWSER_SESSION_TERMINATED",
                    "message": "The browser session has been terminated. The remote browser is no longer available.",
                },
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["task_completed"] is True
        assert body["executionStatus"] == "FAILED"
        assert "errorDetails" in body
        assert body["errorDetails"]["code"] == "BROWSER_SESSION_TERMINATED"

    def test_task_status_handler_exception(self, mock_boto3: Mock) -> None:
        """Test task status with exception."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.task_status_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_terminate_workflow_handler_invalid_json(self, mock_boto3: Mock) -> None:
        """Test workflow termination with invalid JSON."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = "invalid json"

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_terminate_workflow_handler_missing_token(self, mock_boto3: Mock) -> None:
        """Test workflow termination with missing token."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({})

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_terminate_workflow_handler_not_found(self, mock_boto3: Mock) -> None:
        """Test workflow termination with non-existent workflow."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.NOT_FOUND

    def test_terminate_workflow_handler_missing_execution_arn(self, mock_boto3: Mock) -> None:
        """Test workflow termination with missing executionArn."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "PENDING_HUMAN_INPUT",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
                # Missing executionArn intentionally
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_terminate_workflow_handler_exception(self, mock_boto3: Mock) -> None:
        """Test workflow termination with exception."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_view_details_handler_invalid_json(self, mock_boto3: Mock) -> None:
        """Test view details with invalid JSON."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = "invalid json"

        result = handler.view_details_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_view_details_handler_missing_token(self, mock_boto3: Mock) -> None:
        """Test view details with missing token."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({})

        result = handler.view_details_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_view_details_handler_not_found(self, mock_boto3: Mock) -> None:
        """Test view details with non-existent workflow."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.view_details_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.NOT_FOUND

    def test_view_details_handler_no_ttl(self, mock_boto3: Mock) -> None:
        """Test view details with missing TTL."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-token",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test:test",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "PENDING_HUMAN_INPUT",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.view_details_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["expirationTime"] is not None

    def test_view_details_handler_exception(self, mock_boto3: Mock) -> None:
        """Test view details with exception."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.view_details_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_get_browser_session_info_with_datetime_in_response(self, mock_boto3: Mock) -> None:
        """Test browser session info with datetime objects in response."""
        from datetime import datetime

        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {
                "status": "RUNNING",
                "sessionId": "test-session",
                "streams": {"liveViewStream": {"url": "wss://test.com"}},
                "createdAt": datetime(2025, 10, 21, 10, 0, 0),
            }
            mock_browser_instance.generate_live_view_url.return_value = "https://presigned.com"

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            result = handler.get_browser_session_info(event, Mock())

            assert isinstance(result, dict)
            assert result["statusCode"] == HTTPStatus.OK
            body = json.loads(result["body"])  # type: ignore[arg-type]
            assert "createdAt" in body
            assert isinstance(body["createdAt"], str)  # Should be converted to ISO format

    def test_get_browser_session_info_with_list_in_response(self, mock_boto3: Mock) -> None:
        """Test browser session info with list in response data."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {
                "status": "RUNNING",
                "sessionId": "test-session",
                "streams": {"liveViewStream": {"url": "wss://test.com"}},
                "tags": ["tag1", "tag2", "tag3"],
            }
            mock_browser_instance.generate_live_view_url.return_value = "https://presigned.com"

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            result = handler.get_browser_session_info(event, Mock())

            assert isinstance(result, dict)
            assert result["statusCode"] == HTTPStatus.OK
            body = json.loads(result["body"])  # type: ignore[arg-type]
            assert body["tags"] == ["tag1", "tag2", "tag3"]

    def test_get_browser_session_info_empty_session_id(self, mock_boto3: Mock) -> None:
        """Test browser session info with empty session_id."""
        handler = UITakeoverApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": ""}})

        result = handler.get_browser_session_info(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_get_browser_session_info_invalid_response_data_type(self, mock_boto3: Mock) -> None:
        """Test browser session info with invalid response data type."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            # Return a non-dict that will fail the isinstance check
            mock_browser_instance.client.get_browser_session.return_value = "invalid"
            mock_browser_instance.generate_live_view_url.return_value = "https://presigned.com"

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            try:
                handler.get_browser_session_info(event, Mock())
                assert False, "Should have raised TypeError"
            except TypeError as e:
                assert "string indices must be integers" in str(e)

    def test_get_browser_session_info_invalid_streams_type(self, mock_boto3: Mock) -> None:
        """Test browser session info with invalid streams type."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {
                "status": "RUNNING",
                "sessionId": "test-session",
                "streams": "invalid",  # Not a dict
            }
            mock_browser_instance.generate_live_view_url.return_value = "https://presigned.com"

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            try:
                handler.get_browser_session_info(event, Mock())
                assert False, "Should have raised TypeError"
            except TypeError as e:
                assert "Expected streams to be dict" in str(e)

    def test_get_browser_session_info_invalid_live_view_stream_type(self, mock_boto3: Mock) -> None:
        """Test browser session info with invalid liveViewStream type."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {
                "status": "RUNNING",
                "sessionId": "test-session",
                "streams": {"liveViewStream": "invalid"},  # Not a dict
            }
            mock_browser_instance.generate_live_view_url.return_value = "https://presigned.com"

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            try:
                handler.get_browser_session_info(event, Mock())
                assert False, "Should have raised TypeError"
            except TypeError as e:
                assert "Expected liveViewStream to be dict" in str(e)

    def test_get_browser_session_info_terminated_dynamodb_update_failure(self, mock_boto3: Mock) -> None:
        """Test browser session terminated with DynamoDB update failure still raises RuntimeError."""
        with patch("amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.BrowserClient") as mock_browser:
            mock_browser_instance = Mock()
            mock_browser.return_value = mock_browser_instance
            mock_browser_instance.client.get_browser_session.return_value = {"status": "TERMINATED"}

            # Make DynamoDB update fail
            mock_table = Mock()
            mock_table.update_item.side_effect = Exception("DynamoDB error")
            mock_boto3.resource().Table.return_value = mock_table

            handler = UITakeoverApiHandler()
            event = Mock(spec=APIGatewayProxyEvent)
            event.body = json.dumps({"token": "test-token", "remote_browser": {"session_id": "test-session"}})

            # Should still raise RuntimeError even if DynamoDB update fails
            try:
                handler.get_browser_session_info(event, Mock())
                assert False, "Expected RuntimeError to be raised"
            except RuntimeError as e:
                assert "Remote browser has been terminated" in str(e)

            # Verify update was attempted
            mock_table.update_item.assert_called_once()
