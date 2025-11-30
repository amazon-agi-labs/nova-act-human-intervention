import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import (
    BrowserSessionContext,
    EmailContactInfo,
    ExecutionStatus,
    InterventionContext,
    NotificationRecipient,
    UITakeoverRequest,
    UseCase,
)

from amzn_nova_act_human_intervention_client.credentials import AssumedRoleCredentialsProvider
from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors.websocket.ui_takeover import UITakeoverInterventionExecutor


class TestUITakeoverInterventionExecutor:
    @pytest.fixture
    def intervention_context(self):
        return InterventionContext(workflow_run_id="run1", act_session_id="session1", act_id="act1")

    @pytest.fixture
    def browser_session(self):
        return BrowserSessionContext(session_id="browser123")

    @pytest.fixture
    def ui_takeover_request(self, browser_session):
        return UITakeoverRequest(
            message="Test message",
            browser_session=browser_session,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="test@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
        )

    @pytest.fixture
    def client(self, intervention_context):
        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }
        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            return UITakeoverInterventionExecutor(
                "ws://test", intervention_context, credentials_provider=credentials_provider
            )

    def test_init(self, client, intervention_context):
        assert client._endpoint == "ws://test"
        assert client._intervention_context == intervention_context

    @patch("uuid.uuid4")
    def test_create_message(self, mock_uuid, client, ui_takeover_request):
        mock_uuid.return_value = "test-uuid"

        message = client._create_message(ui_takeover_request)

        assert message["action"] == "start-hitl-flow"
        assert message["input"]["session_id"] == "session1"
        assert message["input"]["act_id"] == "act1"
        assert message["input"]["type"] == UseCase.UI_TAKEOVER
        assert message["input"]["message"] == "Test message"
        assert message["input"]["remote_browser"]["session_id"] == "browser123"

    def test_on_message_workflow_started(self, client):
        """Test handling of workflow_started message."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_started",
                "eventId": "event-123",
                "workflowRunId": "workflow-456",
                "sessionId": "session-789",
                "spaUrl": "https://example.com/spa",
                "message": "UI Takeover started",
            }
        )

        client._on_message(mock_app, message)

        assert client._is_reconnecting is False

    def test_on_message_workflow_completed_success(self, client):
        """Test handling of workflow_completed message with success status."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": ExecutionStatus.COMPLETED.value,
                "message": "UI Takeover completed successfully",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client.completion_response is not None
        assert client.completion_response["eventId"] == "event-123"
        assert client._exception is None

    def test_on_message_workflow_completed_failed(self, client):
        """Test handling of workflow_completed message with FAILED status."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": ExecutionStatus.FAILED.value,
                "message": "UI Takeover failed",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client._exception is not None
        assert isinstance(client._exception, RuntimeError)
        assert "UI Takeover workflow failed" in str(client._exception)

    def test_on_message_workflow_completed_terminated(self, client):
        """Test handling of workflow_completed message with TERMINATED status."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": ExecutionStatus.TERMINATED.value,
                "message": "UI Takeover terminated",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client._exception is not None
        assert isinstance(client._exception, WorkflowExecutionError)
        assert "UI Takeover workflow failed" in str(client._exception)
        assert client._exception.status == ExecutionStatus.TERMINATED
        assert client._exception.workflow_type == "UI Takeover"

    def test_on_message_workflow_completed_null_status(self, client):
        """Test handling of workflow_completed message with null executionStatus."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": None,
                "message": "Status missing",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client._exception is not None
        assert isinstance(client._exception, RuntimeError)
        assert "null executionStatus" in str(client._exception)

    def test_on_message_other_message_type(self, client):
        """Test handling of other message types."""
        mock_app = Mock()
        message = json.dumps({"type": "custom_message", "data": "some data"})

        # Should not raise an exception, just log
        client._on_message(mock_app, message)
