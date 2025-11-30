"""Integration tests for notification system with Secrets Manager.

This module tests the complete flow from NotificationFactory through SlackNotifier
to ensure Secrets Manager integration works correctly.
"""

import json
from typing import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalOption,
    ApprovalStepFunctionInput,
    NotificationRecipient,
    SlackContactInfo,
    SlackTargetType,
    UseCase,
)

from amzn_nova_act_human_intervention.notifications.notification_factory import NotificationFactory


class TestNotificationIntegration:
    """Integration tests for notification system."""

    @pytest.fixture
    def mock_secrets_manager(self) -> Generator[MagicMock, None, None]:
        """Mock boto3 Secrets Manager client."""
        with patch("amzn_nova_act_human_intervention.notifications.slack_notifier.boto3.client") as mock_boto:
            mock_sm_client = MagicMock()
            mock_boto.return_value = mock_sm_client
            # Mock successful Secrets Manager response with use case-based tokens
            mock_sm_client.get_secret_value.return_value = {
                "SecretString": json.dumps(
                    {"UITakeover": "xoxb-integration-test-token", "Approval": "xoxb-integration-test-token"}
                )
            }
            yield mock_sm_client

    @pytest.fixture
    def mock_slack_client(self) -> Generator[MagicMock, None, None]:
        """Mock Slack WebClient."""
        with patch("amzn_nova_act_human_intervention.notifications.slack_notifier.WebClient") as mock_client:
            mock_instance = MagicMock()
            # Mock the response with .validate() chain
            mock_response = MagicMock()
            response_data = {
                "ts": "1234567890.123456",
                "channel": "C12345678",
            }
            # Support both dict access (response['ts']) and method call (response.get(key="ts"))
            mock_response.__getitem__.side_effect = lambda key: response_data[key]
            mock_response.get.side_effect = lambda key: response_data.get(key)
            mock_instance.chat_postMessage.return_value.validate.return_value = mock_response
            mock_client.return_value = mock_instance
            yield mock_instance

    @patch.dict(
        "os.environ",
        {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]', "SLACK_SECRETS": "test-slack-secret"},
    )
    def test_notification_factory_initializes_with_secrets_manager(
        self, mock_secrets_manager: Mock, mock_slack_client: Mock
    ) -> None:
        """Test NotificationFactory successfully initializes SlackNotifier from Secrets Manager."""
        factory = NotificationFactory()

        assert factory.slack_notifier is not None
        # Verify Secrets Manager was called
        mock_secrets_manager.get_secret_value.assert_called_once_with(SecretId="test-slack-secret")

    @patch.dict(
        "os.environ",
        {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]', "SLACK_SECRETS": "test-slack-secret"},
    )
    def test_end_to_end_notification_send(self, mock_secrets_manager: Mock, mock_slack_client: Mock) -> None:
        """Test end-to-end notification flow from factory to Slack API."""
        factory = NotificationFactory()

        # Create test request
        request = ApprovalStepFunctionInput(
            workflow_run_id="wf-integration-test",
            session_id="sess-integration-test",
            act_id="act-integration-test",
            event_id="event-integration-test",
            type=UseCase.APPROVAL,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=SlackContactInfo(
                        channel="#test-channel", target="@testuser", target_type=SlackTargetType.USER
                    )
                )
            ],
            query="Integration test approval request",
            options=[
                ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
                ApprovalOption(label="Deny", action=ApprovalAction.DENY),
            ],
            most_recent_screenshot="https://example.com/screenshot.png",
        )

        # Send notification
        result = factory.send_spa_url_notification(request, "https://example.com/approval-link")

        # Verify notification was sent and SlackResponse contains expected fields
        assert result is not None
        assert result["ts"] == "1234567890.123456"
        assert result["channel"] == "C12345678"

        # Verify Slack API was called
        mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#test-channel"
        assert "blocks" in call_kwargs
        assert len(call_kwargs["blocks"]) == 4  # REQUEST_SENT has 4 blocks

    @patch.dict(
        "os.environ",
        {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]', "SLACK_SECRETS": "test-slack-secret"},
    )
    def test_secrets_manager_failure_prevents_initialization(self, mock_secrets_manager: Mock) -> None:
        """Test that Secrets Manager failures prevent NotificationFactory initialization."""
        # Mock Secrets Manager error
        mock_secrets_manager.get_secret_value.side_effect = Exception("Secrets Manager error")

        with pytest.raises(ValueError, match="Failed to retrieve Slack bot tokens from Secrets Manager"):
            NotificationFactory()

    @patch.dict(
        "os.environ",
        {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]', "SLACK_SECRETS": "test-slack-secret"},
    )
    def test_invalid_secret_format_prevents_initialization(self, mock_secrets_manager: Mock) -> None:
        """Test that invalid secret format prevents NotificationFactory initialization."""
        # Mock Secrets Manager with invalid secret format
        mock_secrets_manager.get_secret_value.return_value = {"SecretString": json.dumps({"wrongField": "value"})}

        with pytest.raises(ValueError, match="does not contain any valid bot tokens"):
            NotificationFactory()

    @patch.dict(
        "os.environ",
        {"SUPPORTED_NOTIFICATION_CHANNELS": '["Slack"]', "SLACK_SECRETS": "test-slack-secret"},
    )
    def test_message_builder_integration(self, mock_secrets_manager: Mock, mock_slack_client: Mock) -> None:
        """Test that SlackMessageBuilder is properly integrated and formats messages correctly."""
        factory = NotificationFactory()

        request = ApprovalStepFunctionInput(
            workflow_run_id="wf-test",
            session_id="sess-test",
            act_id="act-test",
            event_id="event-test",
            type=UseCase.APPROVAL,
            timeout=3600,
            notification_recipients=[
                NotificationRecipient(
                    contact_info=SlackContactInfo(
                        channel="#general",
                        target="U12345",
                        target_type=SlackTargetType.USER,  # User ID format
                    )
                )
            ],
            query="Test query with user ID",
            options=[
                ApprovalOption(label="Yes", action=ApprovalAction.APPROVE),
                ApprovalOption(label="No", action=ApprovalAction.DENY),
            ],
            most_recent_screenshot="https://example.com/screenshot.png",
        )

        factory.send_spa_url_notification(request, "https://example.com/link")

        # Verify message builder created proper blocks
        call_kwargs = mock_slack_client.chat_postMessage.call_args[1]
        blocks = call_kwargs["blocks"]

        # First block should contain user mention
        assert blocks[0]["type"] == "section"
        assert "<@U12345>" in blocks[0]["text"]["text"]  # User ID properly formatted

        # Second block should contain quoted message
        assert blocks[1]["type"] == "section"
        assert "> Test query with user ID" in blocks[1]["text"]["text"]

        # Fourth block should be action with Review Request button (no Acknowledge)
        assert blocks[3]["type"] == "actions"
        assert len(blocks[3]["elements"]) == 1
        assert blocks[3]["elements"][0]["text"]["text"] == "Review Request"
