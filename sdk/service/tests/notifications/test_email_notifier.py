"""Tests for Email notifier module."""

from typing import List
from unittest.mock import Mock, patch

from amzn_nova_act_human_intervention_common import EmailContactInfo, SlackContactInfo, UseCase
from botocore.exceptions import ClientError

from amzn_nova_act_human_intervention.notifications.base import NotificationData, NotificationType
from amzn_nova_act_human_intervention.notifications.email_notifier import EmailNotifier


class TestEmailNotifier:
    """Test cases for EmailNotifier class."""

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_init_success(self, mock_boto3: Mock) -> None:
        """Test successful initialization."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()

        assert notifier.ses == mock_ses
        mock_boto3.client.assert_called_once_with("ses", region_name="us-west-2")

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_ui_takeover_success(self, mock_boto3: Mock) -> None:
        """Test successful email send for UI Takeover use case."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        assert result is True
        mock_ses.send_email.assert_called_once()

        # Verify call arguments
        call_args = mock_ses.send_email.call_args
        assert call_args[1]["Source"] == "noreply@example.com"
        assert call_args[1]["Destination"]["ToAddresses"] == ["user@example.com"]

        # Verify subject
        message = call_args[1]["Message"]
        assert message["Subject"]["Data"] == "🖥️ Browser Control Session Ready"

        # Verify HTML body contains key elements
        html_body = message["Body"]["Html"]["Data"]
        assert "Browser Control Session" in html_body
        assert "wf-123" in html_body
        assert "sess-123" in html_body
        assert "act-123" in html_body
        assert "https://example.com/link" in html_body
        assert "2025-10-21T12:00:00Z" in html_body

        # Verify text body
        text_body = message["Body"]["Text"]["Data"]
        assert "BROWSER CONTROL SESSION" in text_body
        assert "wf-123" in text_body

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_approval_success(self, mock_boto3: Mock) -> None:
        """Test successful email send for Approval use case."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(
            to_email_address="approver@example.com", from_email_address="noreply@example.com"
        )
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-456",
            session_id="sess-456",
            act_id="act-456",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-22T14:00:00Z",
            temporary_link="https://example.com/approve",
            message="Test approval message",
        )

        result = notifier.send(data)

        assert result is True

        # Verify call arguments
        call_args = mock_ses.send_email.call_args
        message = call_args[1]["Message"]

        # Verify subject for approval
        assert message["Subject"]["Data"] == "✅ Approval Request"

        # Verify HTML body contains approval-specific text
        html_body = message["Body"]["Html"]["Data"]
        assert "Approval Required" in html_body
        assert "📋 Review & Approve" in html_body

        # Verify text body
        text_body = message["Body"]["Text"]["Data"]
        assert "APPROVAL REQUIRED" in text_body

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_multiple_recipients(self, mock_boto3: Mock) -> None:
        """Test email send to multiple recipients."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contacts: List[EmailContactInfo | SlackContactInfo] = [
            EmailContactInfo(to_email_address="user1@example.com", from_email_address="noreply@example.com"),
            EmailContactInfo(to_email_address="user2@example.com", from_email_address="noreply@example.com"),
            EmailContactInfo(to_email_address="user3@example.com", from_email_address="noreply@example.com"),
        ]
        data = NotificationData(
            recipients=email_contacts,
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        assert result is True
        call_args = mock_ses.send_email.call_args
        assert call_args[1]["Destination"]["ToAddresses"] == [
            "user1@example.com",
            "user2@example.com",
            "user3@example.com",
        ]

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_ses_client_error(self, mock_boto3: Mock) -> None:
        """Test email send with SES ClientError raises exception."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        error_response = {"Error": {"Message": "Invalid email", "Code": "InvalidParameterValue"}}
        mock_ses.send_email.side_effect = ClientError(error_response, "SendEmail")

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(
            to_email_address="invalid@example.com", from_email_address="noreply@example.com"
        )
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        # Should raise ClientError without catching it
        import pytest

        with pytest.raises(ClientError):
            notifier.send(data)

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_generic_exception(self, mock_boto3: Mock) -> None:
        """Test email send with generic exception raises exception."""
        import pytest

        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses
        mock_ses.send_email.side_effect = Exception("Network error")

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        # Should raise Exception without catching it
        with pytest.raises(Exception, match="Network error"):
            notifier.send(data)

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_empty_recipients(self, mock_boto3: Mock) -> None:
        """Test email send with empty recipients list."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        data = NotificationData(
            recipients=[],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        # Empty recipients should return True (no-op success, similar to SlackNotifier)
        assert result is True
        # SES should not be called with empty recipients
        mock_ses.send_email.assert_not_called()

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_html_body_structure_ui_takeover(self, mock_boto3: Mock) -> None:
        """Test HTML body contains all required sections for UI Takeover."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-test",
            session_id="sess-test",
            act_id="act-test",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/test-link",
            message="Test message for browser control",
        )

        notifier.send(data)

        call_args = mock_ses.send_email.call_args
        html_body = call_args[1]["Message"]["Body"]["Html"]["Data"]

        # Verify HTML structure
        assert "<!DOCTYPE html>" in html_body
        assert "<html>" in html_body
        assert "Browser Control Session Ready" in html_body
        assert "Message:" in html_body
        assert "Test message for browser control" in html_body
        assert "Session Details" in html_body
        assert '<a href="https://example.com/test-link"' in html_body
        assert "🔗 Access Browser Control" in html_body
        assert "Important:" in html_body
        assert "This link will expire at" in html_body
        assert "automated message from Nova Act" in html_body

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_html_body_structure_approval(self, mock_boto3: Mock) -> None:
        """Test HTML body contains all required sections for Approval."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-test",
            session_id="sess-test",
            act_id="act-test",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/test-link",
            message="Do you approve this deployment?",
        )

        notifier.send(data)

        call_args = mock_ses.send_email.call_args
        html_body = call_args[1]["Message"]["Body"]["Html"]["Data"]

        # Verify HTML structure
        assert "<!DOCTYPE html>" in html_body
        assert "<html>" in html_body
        assert "Approval Required" in html_body
        assert "Approval Query:" in html_body
        assert "Do you approve this deployment?" in html_body
        assert "Request Details" in html_body
        assert '<a href="https://example.com/test-link"' in html_body
        assert "📋 Review & Approve" in html_body
        assert "Important:" in html_body
        assert "This approval request will expire at" in html_body
        assert "automated message from Nova Act" in html_body

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_text_body_structure(self, mock_boto3: Mock) -> None:
        """Test text body contains all required information."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-text-test",
            session_id="sess-text-test",
            act_id="act-text-test",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/text-link",
            message="Test approval message",
        )

        notifier.send(data)

        call_args = mock_ses.send_email.call_args
        text_body = call_args[1]["Message"]["Body"]["Text"]["Data"]

        # Verify text structure
        assert "APPROVAL REQUIRED" in text_body
        assert "APPROVAL QUERY:" in text_body
        assert "Test approval message" in text_body
        assert "WORKFLOW RUN ID: wf-text-test" in text_body
        assert "SESSION ID: sess-text-test" in text_body
        assert "ACT ID: act-text-test" in text_body
        assert "SECURE ACCESS LINK: https://example.com/text-link" in text_body
        assert "EXPIRES: 2025-10-21T12:00:00Z" in text_body
        assert "IMPORTANT:" in text_body
        assert "This approval request will expire at" in text_body

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_with_custom_from_email(self, mock_boto3: Mock) -> None:
        """Test email send with custom from_email_address."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="custom@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        assert result is True
        call_args = mock_ses.send_email.call_args
        # Verify custom from_email is used
        assert call_args[1]["Source"] == "custom@example.com"

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_with_mixed_recipients(self, mock_boto3: Mock) -> None:
        """Test email send with mixed email and non-email recipients."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        slack_contact = SlackContactInfo(channel="#general", target="@user")
        data = NotificationData(
            recipients=[email_contact, slack_contact],  # Mixed types
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        assert result is True
        call_args = mock_ses.send_email.call_args
        # Only email recipient should be included
        assert call_args[1]["Destination"]["ToAddresses"] == ["user@example.com"]

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_only_non_email_recipients(self, mock_boto3: Mock) -> None:
        """Test email send with only non-email recipients."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        slack_contact = SlackContactInfo(channel="#general", target="@user")
        data = NotificationData(
            recipients=[slack_contact],  # Only non-email recipient
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        # Should return True when no email recipients found (no-op success, similar to SlackNotifier)
        assert result is True
        mock_ses.send_email.assert_not_called()

    @patch("amzn_nova_act_human_intervention.notifications.email_notifier.boto3")
    def test_send_multiple_different_from_emails(self, mock_boto3: Mock) -> None:
        """Test email send with multiple different from_email addresses (warning case)."""
        mock_ses = Mock()
        mock_boto3.client.return_value = mock_ses

        notifier = EmailNotifier()
        email_contacts: List[EmailContactInfo | SlackContactInfo] = [
            EmailContactInfo(to_email_address="user1@example.com", from_email_address="noreply1@example.com"),
            EmailContactInfo(
                to_email_address="user2@example.com", from_email_address="noreply2@example.com"
            ),  # Different from_email
            EmailContactInfo(to_email_address="user3@example.com", from_email_address="noreply1@example.com"),
        ]
        data = NotificationData(
            recipients=email_contacts,
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        # Should still succeed, using first from_email
        assert result is True
        call_args = mock_ses.send_email.call_args
        # Should use first from_email
        assert call_args[1]["Source"] == "noreply1@example.com"
        # All recipients should be included
        assert call_args[1]["Destination"]["ToAddresses"] == [
            "user1@example.com",
            "user2@example.com",
            "user3@example.com",
        ]
