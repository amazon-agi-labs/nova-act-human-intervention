"""Tests for Notification Factory module."""

from datetime import timezone
from unittest.mock import Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    ApprovalStepFunctionInput,
    BrowserSessionContext,
    EmailContactInfo,
    NotificationChannel,
    NotificationRecipient,
    SlackContactInfo,
    UITakeoverStepFunctionInput,
    UseCase,
)

from amzn_nova_act_human_intervention.notifications.exceptions import NotificationDeliveryError
from amzn_nova_act_human_intervention.notifications.notification_factory import NotificationFactory


class TestNotificationFactoryInit:
    """Test cases for NotificationFactory initialization."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_init_email_only(self, mock_email_notifier: Mock) -> None:
        """Test initialization with Email channel only."""
        mock_email_instance = Mock()
        mock_email_notifier.return_value = mock_email_instance

        factory = NotificationFactory()

        assert factory.email_notifier == mock_email_instance
        assert factory.slack_notifier is None
        mock_email_notifier.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_init_slack_only(self, mock_slack_notifier: Mock) -> None:
        """Test initialization with Slack channel only."""
        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        assert factory.slack_notifier == mock_slack_instance
        assert factory.email_notifier is None
        mock_slack_notifier.assert_called_once_with()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email", "Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_init_both_channels(self, mock_slack_notifier: Mock, mock_email_notifier: Mock) -> None:
        """Test initialization with both Email and Slack channels."""
        mock_email_instance = Mock()
        mock_slack_instance = Mock()
        mock_email_notifier.return_value = mock_email_instance
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        assert factory.email_notifier == mock_email_instance
        assert factory.slack_notifier == mock_slack_instance
        mock_email_notifier.assert_called_once()
        mock_slack_notifier.assert_called_once_with()

    @patch.dict("os.environ", {}, clear=True)
    def test_init_missing_env_var(self) -> None:
        """Test initialization fails when SUPPORTED_NOTIFICATION_CHANNELS is missing."""
        with pytest.raises(ValueError, match="SUPPORTED_NOTIFICATION_CHANNELS must be a non-empty list"):
            NotificationFactory()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": "[]"})
    def test_init_empty_list(self) -> None:
        """Test initialization fails when SUPPORTED_NOTIFICATION_CHANNELS is empty."""
        with pytest.raises(ValueError, match="SUPPORTED_NOTIFICATION_CHANNELS must be a non-empty list"):
            NotificationFactory()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '{"invalid": "json"}'})
    def test_init_invalid_json_type(self) -> None:
        """Test initialization fails when SUPPORTED_NOTIFICATION_CHANNELS is not a list."""
        with pytest.raises(ValueError, match="SUPPORTED_NOTIFICATION_CHANNELS must be a non-empty list"):
            NotificationFactory()


class TestSendSpaUrlNotification:
    """Test cases for send_spa_url_notification method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_send_spa_url_notification_ui_takeover(self, mock_email_notifier: Mock) -> None:
        """Test sending SPA URL notification for UI Takeover use case."""
        mock_email_instance = Mock()
        mock_email_instance.send.return_value = True
        mock_email_notifier.return_value = mock_email_instance

        factory = NotificationFactory()
        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        result = factory.send_spa_url_notification(request, "https://example.com/link")

        assert result is None  # Email notifications don't return thread info
        mock_email_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_send_spa_url_notification_approval(self, mock_email_notifier: Mock) -> None:
        """Test sending SPA URL notification for Approval use case."""
        mock_email_instance = Mock()
        mock_email_instance.send.return_value = True
        mock_email_notifier.return_value = mock_email_instance

        factory = NotificationFactory()
        request = ApprovalStepFunctionInput(
            workflow_run_id="wf-456",
            session_id="sess-456",
            act_id="act-456",
            event_id="event-456",
            type=UseCase.APPROVAL,
            timeout=7200,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="approver@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            query="Approve this action?",
            options=[
                ApprovalOption(label="Yes", action=ApprovalAction.APPROVE),
                ApprovalOption(label="No", action=ApprovalAction.DENY),
            ],
            most_recent_screenshot="data:image/png;base64,abc123",
        )

        result = factory.send_spa_url_notification(request, "https://example.com/approve")

        assert result is None  # Email notifications don't return thread info
        mock_email_instance.send.assert_called_once()


class TestSendSpaUrlNotificationContinued:
    """Additional test cases for send_spa_url_notification method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_send_spa_url_notification_email_success(self, mock_email_notifier: Mock) -> None:
        """Test sending SPA URL notification via Email successfully."""
        mock_email_instance = Mock()
        mock_email_instance.send.return_value = True
        mock_email_notifier.return_value = mock_email_instance

        factory = NotificationFactory()
        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        result = factory.send_spa_url_notification(request, "https://example.com/link")

        assert result is None  # Email notifications don't return thread info
        mock_email_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_spa_url_notification_slack_success(self, mock_slack_notifier: Mock) -> None:
        """Test sending SPA URL notification via Slack successfully."""
        mock_slack_instance = Mock()
        mock_slack_instance.send_message.return_value = {"ts": "123.456", "channel": "C123456"}
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@user"))
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        result = factory.send_spa_url_notification(request, "https://example.com/link")

        assert result == {"ts": "123.456", "channel": "C123456"}
        mock_slack_instance.send_message.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email", "Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_spa_url_notification_both_channels_success(
        self, mock_slack_notifier: Mock, mock_email_notifier: Mock
    ) -> None:
        """Test sending SPA URL notification via both channels successfully."""
        mock_email_instance = Mock()
        mock_slack_instance = Mock()
        mock_email_instance.send.return_value = True
        mock_slack_instance.send_message.return_value = {"ts": "123.456", "channel": "C123456"}
        mock_email_notifier.return_value = mock_email_instance
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com", from_email_address="noreply@example.com"
                    )
                ),
                NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@user")),
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        result = factory.send_spa_url_notification(request, "https://example.com/link")

        assert result == {"ts": "123.456", "channel": "C123456"}
        mock_email_instance.send.assert_called_once()
        mock_slack_instance.send_message.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_send_spa_url_notification_email_failure(self, mock_email_notifier: Mock) -> None:
        """Test sending SPA URL notification via Email with failure raises RuntimeError."""
        mock_email_instance = Mock()
        mock_email_instance.send.side_effect = Exception("Email send failed")
        mock_email_notifier.return_value = mock_email_instance

        factory = NotificationFactory()
        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com", from_email_address="noreply@example.com"
                    )
                )
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        with pytest.raises(NotificationDeliveryError, match="Notification delivery failed for channels"):
            factory.send_spa_url_notification(request, "https://example.com/link")

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email", "Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_spa_url_notification_partial_failure(
        self, mock_slack_notifier: Mock, mock_email_notifier: Mock
    ) -> None:
        """Test sending SPA URL notification with one channel failing raises NotificationDeliveryError."""
        mock_email_instance = Mock()
        mock_slack_instance = Mock()
        mock_email_instance.send.return_value = True
        mock_slack_instance.send_message.side_effect = Exception("Slack send failed")
        mock_email_notifier.return_value = mock_email_instance
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=EmailContactInfo(
                        to_email_address="user@example.com", from_email_address="noreply@example.com"
                    )
                ),
                NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@user")),
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        with pytest.raises(NotificationDeliveryError, match="Notification delivery failed for channels"):
            factory.send_spa_url_notification(request, "https://example.com/link")

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_spa_url_notification_slack_not_initialized(self, mock_slack_notifier: Mock) -> None:
        """Test sending SPA URL notification when SlackNotifier is not initialized raises NotificationDeliveryError."""
        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        # Simulate SlackNotifier not being initialized
        factory.slack_notifier = None

        request = UITakeoverStepFunctionInput(
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            event_id="event-123",
            type=UseCase.UI_TAKEOVER,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@user"))
            ],
            message="Test message",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

        with pytest.raises(NotificationDeliveryError, match="Notification delivery failed for channels"):
            factory.send_spa_url_notification(request, "https://example.com/link")


class TestGroupRecipientsByChannel:
    """Test cases for _group_recipients_by_channel method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_group_single_channel(self, mock_email_notifier: Mock) -> None:
        """Test grouping recipients with single channel."""
        factory = NotificationFactory()
        recipients = [
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user1@example.com", from_email_address="noreply@example.com"
                )
            ),
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user2@example.com", from_email_address="noreply@example.com"
                )
            ),
        ]

        grouped = factory._group_recipients_by_channel(recipients)

        assert len(grouped) == 1
        assert NotificationChannel.EMAIL in grouped
        assert len(grouped[NotificationChannel.EMAIL]) == 2

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email", "Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_group_multiple_channels(self, mock_slack_notifier: Mock, mock_email_notifier: Mock) -> None:
        """Test grouping recipients with multiple channels."""
        factory = NotificationFactory()
        recipients = [
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user1@example.com", from_email_address="noreply@example.com"
                )
            ),
            NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@user2")),
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user3@example.com", from_email_address="noreply@example.com"
                )
            ),
        ]

        grouped = factory._group_recipients_by_channel(recipients)

        assert len(grouped) == 2
        assert NotificationChannel.EMAIL in grouped
        assert NotificationChannel.SLACK in grouped
        assert len(grouped[NotificationChannel.EMAIL]) == 2
        assert len(grouped[NotificationChannel.SLACK]) == 1


class TestCalculateExpirationTime:
    """Test cases for _calculate_expiration_time static method."""

    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.datetime")
    def test_calculate_expiration_time(self, mock_datetime: Mock) -> None:
        """Test expiration time calculation."""
        # Mock current time: 2025-10-21 10:00:00 UTC
        mock_now = Mock()
        mock_now.timestamp.return_value = 1729504800.0  # Unix timestamp
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone = timezone

        timeout_seconds = 3600  # 1 hour

        result = NotificationFactory._calculate_expiration_time(timeout_seconds)

        assert "UTC" in result
        assert isinstance(result, str)
        # The result should be 1 hour after the mock time

    def test_calculate_expiration_time_various_timeouts(self) -> None:
        """Test expiration time calculation with various timeouts."""
        timeout_1_hour = 3600
        timeout_24_hours = 86400

        result_1 = NotificationFactory._calculate_expiration_time(timeout_1_hour)
        result_24 = NotificationFactory._calculate_expiration_time(timeout_24_hours)

        assert "UTC" in result_1
        assert "UTC" in result_24
        assert isinstance(result_1, str)
        assert isinstance(result_24, str)


class TestSendExpirationNotification:
    """Test cases for send_expiration_notification method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_expiration_notification_success(self, mock_slack_notifier: Mock) -> None:
        """Test successful expiration notification via Slack."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.PENDING_HUMAN_INPUT,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_expiration_notification(execution_item)

        assert result is True
        mock_slack_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_expiration_notification_no_recipients(self, mock_slack_notifier: Mock) -> None:
        """Test expiration notification with no recipients."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[],  # Empty recipients
            executionStatus=ExecutionStatus.PENDING_HUMAN_INPUT,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_expiration_notification(execution_item)

        assert result is False
        mock_slack_instance.send.assert_not_called()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_expiration_notification_with_threading(self, mock_slack_notifier: Mock) -> None:
        """Test expiration notification with Slack threading support."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.PENDING_HUMAN_INPUT,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
            slackThreadTs="1234567890.123456",  # Thread timestamp present
        )

        result = factory.send_expiration_notification(execution_item)

        assert result is True
        # Verify send was called with thread info
        call_args = mock_slack_instance.send.call_args[0][0]
        assert call_args.slack_thread_identifier == "1234567890.123456"

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_expiration_notification_slack_not_initialized(self, mock_slack_notifier: Mock) -> None:
        """Test expiration notification when SlackNotifier is not initialized."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        # Simulate SlackNotifier not being initialized
        factory.slack_notifier = None

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.PENDING_HUMAN_INPUT,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_expiration_notification(execution_item)

        assert result is False

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_expiration_notification_slack_send_fails(self, mock_slack_notifier: Mock) -> None:
        """Test expiration notification when Slack send fails."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = False
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.PENDING_HUMAN_INPUT,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_expiration_notification(execution_item)

        assert result is False
        mock_slack_instance.send.assert_called_once()


class TestSendApprovalResponseNotification:
    """Test cases for send_approval_response_notification method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_approval_response_approved(self, mock_slack_notifier: Mock) -> None:
        """Test approval response notification for APPROVE action."""
        from amzn_nova_act_human_intervention_common import ApprovalAction, ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_approval_response_notification(execution_item, ApprovalAction.APPROVE.value)

        assert result is True
        mock_slack_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_approval_response_denied(self, mock_slack_notifier: Mock) -> None:
        """Test approval response notification for DENY action."""
        from amzn_nova_act_human_intervention_common import ApprovalAction, ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_approval_response_notification(execution_item, ApprovalAction.DENY.value)

        assert result is True
        mock_slack_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_approval_response_unknown_action(self, mock_slack_notifier: Mock) -> None:
        """Test approval response notification with unknown action."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_approval_response_notification(execution_item, "UNKNOWN_ACTION")

        assert result is False
        mock_slack_instance.send.assert_not_called()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_approval_response_no_recipients(self, mock_slack_notifier: Mock) -> None:
        """Test approval response notification with no recipients."""
        from amzn_nova_act_human_intervention_common import ApprovalAction, ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[],  # Empty recipients
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_approval_response_notification(execution_item, ApprovalAction.APPROVE.value)

        assert result is False
        mock_slack_instance.send.assert_not_called()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_approval_response_slack_not_initialized(self, mock_slack_notifier: Mock) -> None:
        """Test approval response notification when SlackNotifier is not initialized."""
        from amzn_nova_act_human_intervention_common import ApprovalAction, ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        # Simulate SlackNotifier not being initialized
        factory.slack_notifier = None

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_approval_response_notification(execution_item, ApprovalAction.APPROVE.value)

        assert result is False

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_approval_response_slack_send_fails(self, mock_slack_notifier: Mock) -> None:
        """Test approval response notification when Slack send fails."""
        from amzn_nova_act_human_intervention_common import ApprovalAction, ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = False
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.APPROVAL,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_approval_response_notification(execution_item, ApprovalAction.APPROVE.value)

        assert result is False
        mock_slack_instance.send.assert_called_once()


class TestSendTaskCompletionNotification:
    """Test cases for send_task_completion_notification method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_task_completion_notification_success(self, mock_slack_notifier: Mock) -> None:
        """Test successful task completion notification."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_task_completion_notification(execution_item)

        assert result is True
        mock_slack_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_task_completion_notification_no_recipients(self, mock_slack_notifier: Mock) -> None:
        """Test task completion notification with no recipients."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[],  # Empty recipients
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_task_completion_notification(execution_item)

        assert result is False
        mock_slack_instance.send.assert_not_called()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_task_completion_notification_slack_not_initialized(self, mock_slack_notifier: Mock) -> None:
        """Test task completion notification when SlackNotifier is not initialized."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        # Simulate SlackNotifier not being initialized
        factory.slack_notifier = None

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_task_completion_notification(execution_item)

        assert result is False

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_task_completion_notification_slack_send_fails(self, mock_slack_notifier: Mock) -> None:
        """Test task completion notification when Slack send fails."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = False
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.COMPLETED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_task_completion_notification(execution_item)

        assert result is False
        mock_slack_instance.send.assert_called_once()


class TestGetSpaMessage:
    """Test cases for _get_spa_message method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Email"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.EmailNotifier")
    def test_get_spa_message_unknown_request_type(self, mock_email_notifier: Mock) -> None:
        """Test _get_spa_message with unknown request type."""
        factory = NotificationFactory()

        # Create a mock object that's not a valid request type
        invalid_request = Mock()
        invalid_request.type = UseCase.UI_TAKEOVER

        with pytest.raises(ValueError, match="Unknown request type"):
            factory._get_spa_message(invalid_request)


class TestSendTerminationNotification:
    """Test cases for send_termination_notification method."""

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_success(self, mock_slack_notifier: Mock) -> None:
        """Test successful termination notification."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_termination_notification(execution_item)

        assert result is True
        mock_slack_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_approval_workflow(self, mock_slack_notifier: Mock) -> None:
        """Test termination notification for Approval workflow."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-456",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test456",
            workflowRunId="wf-456",
            sessionId="sess-456",
            actId="act-456",
            interventionType=UseCase.APPROVAL,
            timeout=7200,
            notificationRecipients=[
                {"contact_info": {"type": "slack", "channel": "#approvals", "target": "@approver"}}
            ],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567900,
            ttl=1234654290,
            connectionId="conn456",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_termination_notification(execution_item)

        assert result is True
        mock_slack_instance.send.assert_called_once()
        # Verify the message contains the workflow type
        call_args = mock_slack_instance.send.call_args[0][0]
        assert "Approval" in call_args.message

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_no_recipients(self, mock_slack_notifier: Mock) -> None:
        """Test termination notification with no recipients."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[],  # Empty recipients
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_termination_notification(execution_item)

        assert result is False
        mock_slack_instance.send.assert_not_called()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_with_threading(self, mock_slack_notifier: Mock) -> None:
        """Test termination notification with Slack threading support."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
            slackThreadTs="1234567890.123456",  # Thread timestamp present
        )

        result = factory.send_termination_notification(execution_item)

        assert result is True
        # Verify send was called with thread info
        call_args = mock_slack_instance.send.call_args[0][0]
        assert call_args.slack_thread_identifier == "1234567890.123456"

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_slack_not_initialized(self, mock_slack_notifier: Mock) -> None:
        """Test termination notification when SlackNotifier is not initialized."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()
        # Simulate SlackNotifier not being initialized
        factory.slack_notifier = None

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_termination_notification(execution_item)

        assert result is False

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_slack_send_fails(self, mock_slack_notifier: Mock) -> None:
        """Test termination notification when Slack send fails."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = False
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[{"contact_info": {"type": "slack", "channel": "#general", "target": "@user"}}],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_termination_notification(execution_item)

        assert result is False
        mock_slack_instance.send.assert_called_once()

    @patch.dict("os.environ", {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]'})
    @patch("amzn_nova_act_human_intervention.notifications.notification_factory.SlackNotifier")
    def test_send_termination_notification_multiple_recipients(self, mock_slack_notifier: Mock) -> None:
        """Test termination notification with multiple recipients."""
        from amzn_nova_act_human_intervention_common import ExecutionItem, ExecutionStatus, UseCase

        mock_slack_instance = Mock()
        mock_slack_instance.send.return_value = True
        mock_slack_notifier.return_value = mock_slack_instance

        factory = NotificationFactory()

        execution_item = ExecutionItem(
            eventId="event-123",
            executionArn="arn:aws:states:us-west-2:123:execution:test:test123",
            workflowRunId="wf-123",
            sessionId="sess-123",
            actId="act-123",
            interventionType=UseCase.UI_TAKEOVER,
            timeout=3600,
            notificationRecipients=[
                {"contact_info": {"type": "slack", "channel": "#general", "target": "@user1"}},
                {"contact_info": {"type": "slack", "channel": "#alerts", "target": "@user2"}},
            ],
            executionStatus=ExecutionStatus.TERMINATED,
            createdAt=1234567890,
            updatedAt=1234567890,
            ttl=1234567890,
            connectionId="conn123",
            executionEndpoint="wss://test.execute-api.us-west-2.amazonaws.com/prod",
        )

        result = factory.send_termination_notification(execution_item)

        assert result is True
        # Verify send was called (should be called once per channel group)
        assert mock_slack_instance.send.call_count > 0
