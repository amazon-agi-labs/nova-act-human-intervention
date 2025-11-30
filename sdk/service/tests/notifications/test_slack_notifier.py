"""Tests for Slack notifier module (Slack Bot SDK implementation)."""

import json
from typing import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import SlackContactInfo, SlackTargetType, UseCase
from slack_sdk.errors import SlackApiError

from amzn_nova_act_human_intervention.notifications.base import NotificationData, NotificationType
from amzn_nova_act_human_intervention.notifications.slack_notifier import SlackNotifier


class TestSlackNotifier:
    """Test cases for SlackNotifier class (Slack Bot SDK)."""

    @pytest.fixture
    def mock_slack_client(self) -> Generator[MagicMock, None, None]:
        """Mock Slack WebClient."""
        with patch("amzn_nova_act_human_intervention.notifications.slack_notifier.WebClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_secrets_manager(self) -> Generator[MagicMock, None, None]:
        """Mock boto3 Secrets Manager client."""
        with patch("amzn_nova_act_human_intervention.notifications.slack_notifier.boto3.client") as mock_boto:
            mock_sm_client = MagicMock()
            mock_boto.return_value = mock_sm_client
            yield mock_sm_client

    @pytest.fixture
    def mock_secrets_with_tokens(self, mock_secrets_manager: Mock) -> Mock:
        """Mock Secrets Manager with valid tokens for both use cases."""
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"UITakeover": "xoxb-test-token", "Approval": "xoxb-test-token"})
        }
        return mock_secrets_manager

    @patch.dict("os.environ", {}, clear=True)
    def test_init_missing_slack_secrets_env(self) -> None:
        """Test initialization fails when SLACK_SECRETS env var is missing."""
        with pytest.raises(ValueError, match="SLACK_SECRETS environment variable must be set"):
            SlackNotifier()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_init_success_from_secrets_manager(self, mock_secrets_manager: Mock, mock_slack_client: Mock) -> None:
        """Test successful initialization reading bot tokens from Secrets Manager."""
        # Mock Secrets Manager response with new structure
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"UITakeover": "xoxb-ui-takeover-token", "Approval": "xoxb-approval-token"})
        }

        notifier = SlackNotifier()

        assert notifier.bot_tokens[UseCase.UI_TAKEOVER.value] == "xoxb-ui-takeover-token"
        assert notifier.bot_tokens[UseCase.APPROVAL.value] == "xoxb-approval-token"
        assert notifier.message_builder is not None
        mock_secrets_manager.get_secret_value.assert_called_once_with(SecretId="test-slack-secret")

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_init_secrets_manager_missing_token_field(self, mock_secrets_manager: Mock) -> None:
        """Test initialization fails when secret JSON doesn't contain any valid bot tokens."""
        # Mock Secrets Manager response without any use case keys
        mock_secrets_manager.get_secret_value.return_value = {"SecretString": json.dumps({"someOtherField": "value"})}

        with pytest.raises(ValueError, match="Secret 'test-slack-secret' does not contain any valid bot tokens"):
            SlackNotifier()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_init_secrets_manager_invalid_json(self, mock_secrets_manager: Mock) -> None:
        """Test initialization fails when secret contains invalid JSON."""
        # Mock Secrets Manager response with invalid JSON
        mock_secrets_manager.get_secret_value.return_value = {"SecretString": "invalid-json-{{"}

        with pytest.raises(ValueError, match="Failed to retrieve Slack bot tokens from Secrets Manager"):
            SlackNotifier()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_init_secrets_manager_api_error(self, mock_secrets_manager: Mock) -> None:
        """Test initialization fails when Secrets Manager API returns an error."""
        # Mock Secrets Manager API error
        mock_secrets_manager.get_secret_value.side_effect = Exception("Secrets Manager API error")

        with pytest.raises(ValueError, match="Failed to retrieve Slack bot tokens from Secrets Manager"):
            SlackNotifier()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_success_single_recipient(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test successful notification send to single Slack recipient."""
        from unittest.mock import MagicMock

        # Mock successful API response
        mock_response = MagicMock()
        response_data = {
            "ts": "1234567890.123456",
            "channel": "C12345678",
        }
        # Support both dict access (response['ts']) and method call (response.get(key="ts"))
        mock_response.__getitem__.side_effect = lambda key: response_data[key]
        mock_response.get.side_effect = lambda key: response_data.get(key)
        mock_slack_client.chat_postMessage.return_value.validate.return_value = mock_response

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(
            channel="C12345678",
            target="@testuser",
            target_type=SlackTargetType.USER,
        )
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        assert result is True
        mock_slack_client.chat_postMessage.assert_called_once()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_success_multiple_recipients(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test successful notification send to multiple Slack recipients."""
        from unittest.mock import MagicMock

        # Mock successful API response
        mock_response = MagicMock()
        response_data = {
            "ts": "1234567890.123456",
            "channel": "C12345678",
        }
        # Support both dict access (response['ts']) and method call (response.get(key="ts"))
        mock_response.__getitem__.side_effect = lambda key: response_data[key]
        mock_response.get.side_effect = lambda key: response_data.get(key)
        mock_slack_client.chat_postMessage.return_value.validate.return_value = mock_response

        notifier = SlackNotifier()
        slack_contact1 = SlackContactInfo(channel="C12345678", target="@user1", target_type=SlackTargetType.USER)
        slack_contact2 = SlackContactInfo(channel="C87654321", target="U87654321", target_type=SlackTargetType.USER)
        slack_contact3 = SlackContactInfo(channel="C99999999", target="@user3", target_type=SlackTargetType.USER)

        data = NotificationData(
            recipients=[slack_contact1, slack_contact2, slack_contact3],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Test approval message",
        )

        result = notifier.send(data)

        assert result is True
        assert mock_slack_client.chat_postMessage.call_count == 3

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_partial_failure(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test notification send with partial failures."""
        from unittest.mock import MagicMock

        # First call succeeds, second fails
        mock_response_success = MagicMock()
        response_data = {
            "ts": "1234567890.123456",
            "channel": "C12345678",
        }
        # Support both dict access (response['ts']) and method call (response.get(key="ts"))
        mock_response_success.__getitem__.side_effect = lambda key: response_data[key]
        mock_response_success.get.side_effect = lambda key: response_data.get(key)

        mock_slack_client.chat_postMessage.return_value.validate.side_effect = [
            mock_response_success,
            SlackApiError("channel_not_found", {"error": "channel_not_found"}),  # type: ignore[no-untyped-call]
        ]

        notifier = SlackNotifier()
        slack_contact1 = SlackContactInfo(channel="C12345678", target="@user1", target_type=SlackTargetType.USER)
        slack_contact2 = SlackContactInfo(channel="C99999999", target="@user2", target_type=SlackTargetType.USER)

        data = NotificationData(
            recipients=[slack_contact1, slack_contact2],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_COMPLETED,
            message="Test message",
        )

        result = notifier.send(data)

        assert result is False
        assert mock_slack_client.chat_postMessage.call_count == 2

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_slack_api_error(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test notification send with Slack API error."""
        mock_slack_client.chat_postMessage.side_effect = SlackApiError("invalid_auth", {"error": "invalid_auth"})  # type: ignore[no-untyped-call]

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Test message",
        )

        result = notifier.send(data)

        assert result is False

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_generic_exception(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test notification send with generic exception."""
        mock_slack_client.chat_postMessage.side_effect = Exception("Network error")

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Test message",
        )

        result = notifier.send(data)

        assert result is False

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_empty_recipients_list(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test notification send with empty recipients list."""
        notifier = SlackNotifier()
        data = NotificationData(
            recipients=[],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_COMPLETED,
            message="Test message",
        )

        result = notifier.send(data)

        assert result is True  # 0 == 0, all "sent"
        mock_slack_client.chat_postMessage.assert_not_called()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_message_returns_metadata(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test that send_message returns message metadata for non-threaded messages."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        response_data = {
            "ts": "1234567890.123456",
            "channel": "C12345678",
        }
        # Support both dict access (response['ts']) and method call (response.get(key="ts"))
        mock_response.__getitem__.side_effect = lambda key: response_data[key]
        mock_response.get.side_effect = lambda key: response_data.get(key)
        mock_slack_client.chat_postMessage.return_value.validate.return_value = mock_response

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send_message(data, slack_contact)

        assert result is not None
        assert result["ts"] == "1234567890.123456"
        assert result["channel"] == "C12345678"

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_message_with_threading(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test sending message as threaded reply returns None."""
        mock_response = Mock()
        mock_slack_client.chat_postMessage.return_value.validate.return_value = mock_response

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Test message",
            slack_thread_identifier="1234567890.123456",  # Use existing thread
        )

        result = notifier.send_message(data, slack_contact)

        # Threaded messages return None (no need to capture thread info again)
        assert result is None
        # Verify thread_ts was passed to API
        call_kwargs = mock_slack_client.chat_postMessage.call_args[1]
        assert call_kwargs["thread_ts"] == "1234567890.123456"
        # Verify validate was called
        mock_slack_client.chat_postMessage.return_value.validate.assert_called_once()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_message_raises_exception_on_slack_api_error(
        self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock
    ) -> None:
        """Test that send_message raises SlackApiError without handling it."""
        mock_slack_client.chat_postMessage.side_effect = SlackApiError(
            "channel_not_found", {"error": "channel_not_found"}
        )  # type: ignore[no-untyped-call]

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        with pytest.raises(SlackApiError, match="channel_not_found"):
            notifier.send_message(data, slack_contact)

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_message_raises_generic_exception(
        self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock
    ) -> None:
        """Test that send_message raises generic exceptions without handling them."""
        mock_slack_client.chat_postMessage.side_effect = Exception("Network error")

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        with pytest.raises(Exception, match="Network error"):
            notifier.send_message(data, slack_contact)

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_message_threaded_api_error(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test that threaded messages raise API errors from validate() without handling them."""
        mock_slack_client.chat_postMessage.return_value.validate.side_effect = SlackApiError(
            "channel_not_found", {"error": "channel_not_found"}
        )  # type: ignore[no-untyped-call]

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Test message",
            slack_thread_identifier="1234567890.123456",  # Threaded message
        )

        with pytest.raises(SlackApiError, match="channel_not_found"):
            notifier.send_message(data, slack_contact)

        # Verify validate was called
        mock_slack_client.chat_postMessage.return_value.validate.assert_called_once()

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_success_with_threaded_message(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test send() correctly handles threaded messages (returns empty dict)."""
        # Mock successful threaded message response
        mock_response = Mock()
        mock_slack_client.chat_postMessage.return_value.validate.return_value = mock_response

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Test message",
            slack_thread_identifier="1234567890.123456",  # Threaded message
        )

        result = notifier.send(data)

        # Should return True even though send_message returns empty dict for threaded messages
        assert result is True
        mock_slack_client.chat_postMessage.assert_called_once()
        # Verify thread_ts was passed
        call_kwargs = mock_slack_client.chat_postMessage.call_args[1]
        assert call_kwargs["thread_ts"] == "1234567890.123456"

    @patch.dict("os.environ", {"SLACK_SECRETS": "test-slack-secret"})
    def test_send_with_mixed_recipients(self, mock_secrets_with_tokens: Mock, mock_slack_client: Mock) -> None:
        """Test send with mixed Slack and non-Slack recipients (non-Slack skipped)."""
        from unittest.mock import MagicMock

        from amzn_nova_act_human_intervention_common import EmailContactInfo

        # Mock successful API response
        mock_response = MagicMock()
        response_data = {
            "ts": "1234567890.123456",
            "channel": "C12345678",
        }
        # Support both dict access (response['ts']) and method call (response.get(key="ts"))
        mock_response.__getitem__.side_effect = lambda key: response_data[key]
        mock_response.get.side_effect = lambda key: response_data.get(key)
        mock_slack_client.chat_postMessage.return_value.validate.return_value = mock_response

        notifier = SlackNotifier()
        slack_contact = SlackContactInfo(channel="C12345678", target="@user", target_type=SlackTargetType.USER)
        email_contact = EmailContactInfo(to_email_address="test@example.com", from_email_address="noreply@example.com")

        data = NotificationData(
            recipients=[slack_contact, email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        result = notifier.send(data)

        # Should succeed because all Slack recipients sent successfully
        assert result is True
        # Should only send to Slack recipient
        mock_slack_client.chat_postMessage.assert_called_once()
