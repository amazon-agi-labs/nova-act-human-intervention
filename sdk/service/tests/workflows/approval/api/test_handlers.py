"""Tests for Approval API handlers."""

import json
from http import HTTPStatus
from unittest.mock import Mock, patch

from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from amzn_nova_act_human_intervention.workflows.approval.api.handlers import ApprovalApiHandler


@patch.dict(
    "os.environ",
    {"AWS_REGION": "us-west-2", "EXECUTIONS_TABLE": "test-table", "SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'},
)
@patch("amzn_nova_act_human_intervention.workflows.approval.api.handlers.boto3")
class TestApprovalApiHandler:
    def test_record_response_handler_success(self, mock_boto3: Mock) -> None:
        """Test successful approval response recording."""
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
                "interventionType": "Approval",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "PENDING_HUMAN_INPUT",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = ApprovalApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "approvalAction": "APPROVE"})

        result = handler.record_response_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.OK
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert body["task_completed"] is True
        assert body["approvalAction"] == "APPROVE"
        mock_table.update_item.assert_called_once()

    def test_record_response_handler_already_completed(self, mock_boto3: Mock) -> None:
        """Test approval response when task is already completed (replay attack prevention)."""
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
                "interventionType": "Approval",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "COMPLETED",  # Already completed
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
                "approvalAction": "DENY",  # Previously denied
            }
        }

        # Mock ConditionalCheckFailedException when trying to update completed task
        mock_table.meta.client.exceptions.ConditionalCheckFailedException = ClientError
        mock_table.update_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
        )

        handler = ApprovalApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        # Attacker tries to change decision to APPROVE
        event.body = json.dumps({"token": "test-token", "approvalAction": "APPROVE"})

        result = handler.record_response_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.CONFLICT
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert "already completed" in body["error"].lower()
        assert body["currentStatus"] == "COMPLETED"
        # Verify update_item was called (and failed with condition check)
        mock_table.update_item.assert_called_once()

    def test_record_response_handler_invalid_action(self, mock_boto3: Mock) -> None:
        """Test approval response with invalid action."""
        handler = ApprovalApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "approvalAction": "INVALID"})

        result = handler.record_response_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_record_response_handler_missing_token(self, mock_boto3: Mock) -> None:
        """Test approval response with missing token."""
        handler = ApprovalApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"approvalAction": "APPROVE"})

        result = handler.record_response_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.BAD_REQUEST

    def test_record_response_handler_task_not_found(self, mock_boto3: Mock) -> None:
        """Test approval response with non-existent task."""
        mock_table = Mock()
        mock_boto3.resource().Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        handler = ApprovalApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token", "approvalAction": "APPROVE"})

        result = handler.record_response_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.NOT_FOUND

    def test_terminate_workflow_handler_already_completed(self, mock_boto3: Mock) -> None:
        """Test workflow termination when task is already completed (prevents status override)."""
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
                "interventionType": "Approval",
                "timeout": 3600,
                "notificationRecipients": [{"contact_info": {"type": "email", "email_address": "test@example.com"}}],
                "executionStatus": "COMPLETED",  # Already completed with approval
                "approvalAction": "APPROVE",
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        handler = ApprovalApiHandler()
        event = Mock(spec=APIGatewayProxyEvent)
        event.body = json.dumps({"token": "test-token"})

        result = handler.terminate_workflow_handler(event, Mock())

        assert isinstance(result, dict)
        assert result["statusCode"] == HTTPStatus.CONFLICT
        body = json.loads(result["body"])  # type: ignore[arg-type]
        assert "cannot terminate completed task" in body["error"].lower()
        assert body["currentStatus"] == "COMPLETED"
        # Verify Step Functions stop_execution was never called
        mock_boto3.client().stop_execution.assert_not_called()
