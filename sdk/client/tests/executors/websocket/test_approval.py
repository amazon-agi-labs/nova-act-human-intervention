import json
from unittest.mock import Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    ApprovalRequest,
    EmailContactInfo,
    ExecutionStatus,
    InterventionContext,
    NotificationRecipient,
    UseCase,
)

from amzn_nova_act_human_intervention_client.credentials import AssumedRoleCredentialsProvider
from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors.websocket.approval import ApprovalInterventionExecutor


class TestApprovalInterventionExecutor:
    @pytest.fixture
    def intervention_context(self):
        return InterventionContext(workflow_run_id="run1", act_session_id="session1", act_id="act1")

    @pytest.fixture
    def approval_request(self):
        return ApprovalRequest(
            question="Continue?",
            options=[
                ApprovalOption(label="Yes", action=ApprovalAction.APPROVE),
                ApprovalOption(label="No", action=ApprovalAction.DENY),
            ],
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="test@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            most_recent_screenshot="data:image/jpeg;base64,test",
        )

    @pytest.fixture
    def client(self, intervention_context):
        from datetime import datetime, timedelta, timezone

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
        mock_s3_client = Mock()

        with patch("boto3.Session") as mock_session_class, patch("boto3.client", return_value=mock_s3_client):
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            client = ApprovalInterventionExecutor(
                "ws://test",
                intervention_context,
                screenshot_s3_bucket="test-bucket",
                credentials_provider=credentials_provider,
            )
            # Store the mock for test assertions
            client._s3_client = mock_s3_client
            return client

    def test_init(self, client, intervention_context):
        assert client._endpoint == "ws://test"
        assert client._intervention_context == intervention_context

    def test_init_without_screenshot_bucket_raises_error(self, intervention_context):
        """Test that ApprovalInterventionExecutor requires screenshot_s3_bucket."""
        from datetime import datetime, timedelta, timezone

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
            with pytest.raises(ValueError, match="screenshot_s3_bucket is required for ApprovalInterventionExecutor"):
                ApprovalInterventionExecutor(
                    "ws://test",
                    intervention_context,
                    screenshot_s3_bucket="",
                    credentials_provider=credentials_provider,
                )

    def test_init_with_none_screenshot_bucket_raises_error(self, intervention_context):
        """Test that ApprovalInterventionExecutor requires screenshot_s3_bucket (None case)."""
        from datetime import datetime, timedelta, timezone

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
            with pytest.raises(ValueError, match="screenshot_s3_bucket is required for ApprovalInterventionExecutor"):
                ApprovalInterventionExecutor(
                    "ws://test",
                    intervention_context,
                    screenshot_s3_bucket=None,
                    credentials_provider=credentials_provider,  # type: ignore
                )

    @patch("uuid.uuid4")
    def test_create_message_with_options(self, mock_uuid, client, approval_request):
        mock_uuid.return_value = "test-uuid"
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.return_value = "https://s3.url/screenshot"
        client._s3_client = mock_s3_client

        message = client._create_message(approval_request)

        assert message["action"] == "start-hitl-flow"
        assert message["input"]["session_id"] == "session1"
        assert message["input"]["act_id"] == "act1"
        assert message["input"]["type"] == UseCase.APPROVAL
        assert message["input"]["query"] == "Continue?"
        # Options are now ApprovalOption objects with label and action
        assert message["input"]["options"] == [
            {"label": "Yes", "action": "APPROVE"},
            {"label": "No", "action": "DENY"},
        ]
        assert message["input"]["most_recent_screenshot"] == "https://s3.url/screenshot"

    @patch("uuid.uuid4")
    def test_create_message_default_options(self, mock_uuid, client):
        mock_uuid.return_value = "test-uuid"
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.return_value = "https://s3.url/screenshot"
        client._s3_client = mock_s3_client

        request = ApprovalRequest(
            question="Continue?",
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="test@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            most_recent_screenshot="data:image/jpeg;base64,test",
        )

        message = client._create_message(request)

        # Default options are ApprovalOption objects with label and action
        assert message["input"]["options"] == [
            {"label": "Approve", "action": "APPROVE"},
            {"label": "Cancel", "action": "DENY"},
        ]

    @patch("uuid.uuid4")
    def test_create_message_with_screenshot(self, mock_uuid, client):
        mock_uuid.return_value = "test-uuid"
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.return_value = "https://s3.url/screenshot"
        client._s3_client = mock_s3_client

        request = ApprovalRequest(
            question="Continue?",
            options=[
                ApprovalOption(label="Yes", action=ApprovalAction.APPROVE),
                ApprovalOption(label="No", action=ApprovalAction.DENY),
            ],
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="test@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            most_recent_screenshot="data:image/jpeg;base64,original",
        )

        message = client._create_message(request)

        # Verify S3 upload was called with text content
        assert mock_s3_client.put_object.called
        call_kwargs = mock_s3_client.put_object.call_args[1]
        # Verify uploaded as text/plain with complete data URL
        assert call_kwargs["ContentType"] == "text/plain"
        assert call_kwargs["Body"] == b"data:image/jpeg;base64,original"
        assert call_kwargs["Key"].endswith(".txt")
        # Verify presigned URL is used in message
        assert message["input"]["most_recent_screenshot"] == "https://s3.url/screenshot"

    def test_create_message_no_screenshot_raises_validation_error(self):
        """Test that ApprovalRequest requires most_recent_screenshot field."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ApprovalRequest(
                question="Continue?",
                options=[
                    ApprovalOption(label="Yes", action=ApprovalAction.APPROVE),
                    ApprovalOption(label="No", action=ApprovalAction.DENY),
                ],
                notification_recipients=[
                    NotificationRecipient(
                        contact_info=EmailContactInfo(
                            to_email_address="test@example.com", from_email_address="noreply@example.com"
                        )
                    )
                ],
                # most_recent_screenshot is missing - should raise ValidationError
            )

    @patch("uuid.uuid4")
    def test_create_message_with_s3(self, mock_uuid, intervention_context, approval_request):
        """Test that message uses S3 URL and uploads data URL as text."""
        from datetime import datetime, timedelta, timezone

        mock_uuid.return_value = "test-uuid"

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
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/bucket/key?presigned"

        with patch("boto3.Session") as mock_session_class, patch("boto3.client", return_value=mock_s3_client):
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            client = ApprovalInterventionExecutor(
                "ws://test",
                intervention_context,
                screenshot_s3_bucket="test-bucket",
                credentials_provider=credentials_provider,
            )

            message = client._create_message(approval_request)

            # Verify S3 upload was called with text content
            assert mock_s3_client.put_object.called
            call_kwargs = mock_s3_client.put_object.call_args[1]
            # Verify data URL uploaded as text
            assert call_kwargs["ContentType"] == "text/plain"
            assert call_kwargs["Body"] == approval_request.most_recent_screenshot.encode("utf-8")
            assert call_kwargs["Key"].endswith(".txt")
            # Verify message uses S3 presigned URL
            assert message["input"]["most_recent_screenshot"].startswith("https://s3.amazonaws.com")
            assert message["input"]["most_recent_screenshot"] == "https://s3.amazonaws.com/bucket/key?presigned"

    def test_upload_screenshot_with_invalid_data_url_raises_error(self, client):
        """Test that _upload_screenshot_to_s3 raises ValueError for invalid data URL format."""
        invalid_data_url = "https://example.com/image.png"  # Not a data URL
        event_id = "test-event-123"

        with pytest.raises(ValueError, match="Invalid data URL format - must start with 'data:'"):
            client._upload_screenshot_to_s3(invalid_data_url, event_id)

    def test_upload_screenshot_with_invalid_data_url_no_prefix(self, client):
        """Test that _upload_screenshot_to_s3 raises ValueError when data URL is missing 'data:' prefix."""
        invalid_data_url = "image/jpeg;base64,dGVzdA=="  # Missing 'data:' prefix
        event_id = "test-event-456"

        with pytest.raises(ValueError, match="Invalid data URL format - must start with 'data:'"):
            client._upload_screenshot_to_s3(invalid_data_url, event_id)

    def test_s3_client_uses_assumed_role_credentials(self, intervention_context):
        """Test that S3 client is created with assumed role credentials and S3v4 signature."""
        from datetime import datetime, timedelta, timezone

        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "assumed_key",
                "SecretAccessKey": "assumed_secret",
                "SessionToken": "assumed_token",
                "Expiration": expiry_time,
            }
        }

        with patch("boto3.Session") as mock_session_class, patch("boto3.client") as mock_boto_client:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )

            ApprovalInterventionExecutor(
                "ws://test",
                intervention_context,
                screenshot_s3_bucket="test-bucket",
                credentials_provider=credentials_provider,
                region="us-east-1",
            )

            # Verify boto3.client was called with assumed role credentials and S3v4 config
            assert mock_boto_client.called
            call_args = mock_boto_client.call_args

            # Verify S3 client creation
            assert call_args[0][0] == "s3"  # Service name
            assert call_args[1]["region_name"] == "us-east-1"
            assert call_args[1]["aws_access_key_id"] == "assumed_key"
            assert call_args[1]["aws_secret_access_key"] == "assumed_secret"
            assert call_args[1]["aws_session_token"] == "assumed_token"

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
                "message": "Approval workflow started",
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
                "approvalAction": "APPROVE",
                "message": "Approval completed successfully",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client.completion_response is not None
        assert client.completion_response["eventId"] == "event-123"
        assert client.completion_response["approvalAction"] == "APPROVE"
        assert client._exception is None

    def test_on_message_workflow_completed_failed(self, client):
        """Test handling of workflow_completed message with FAILED status."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": ExecutionStatus.FAILED.value,
                "approvalAction": None,
                "message": "Approval workflow failed",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client._exception is not None
        assert isinstance(client._exception, RuntimeError)
        assert "Approval workflow failed" in str(client._exception)

    def test_on_message_workflow_completed_terminated(self, client):
        """Test handling of workflow_completed message with TERMINATED status."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": ExecutionStatus.TERMINATED.value,
                "approvalAction": None,
                "message": "Approval workflow terminated",
            }
        )

        client._on_message(mock_app, message)

        assert client._completion_received is True
        assert client._exception is not None
        assert isinstance(client._exception, WorkflowExecutionError)
        assert "Approval workflow failed" in str(client._exception)
        assert client._exception.status == ExecutionStatus.TERMINATED
        assert client._exception.workflow_type == "Approval"

    def test_on_message_workflow_completed_null_status(self, client):
        """Test handling of workflow_completed message with null executionStatus."""
        mock_app = Mock()
        message = json.dumps(
            {
                "type": "workflow_completed",
                "eventId": "event-123",
                "executionStatus": None,
                "approvalAction": None,
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
