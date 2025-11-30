"""Tests for Slack message builder module."""

from amzn_nova_act_human_intervention_common import SlackContactInfo, SlackTargetType, UseCase

from amzn_nova_act_human_intervention.notifications.base import NotificationData, NotificationType
from amzn_nova_act_human_intervention.notifications.slack_message_builder import SlackMessageBuilder


class TestSlackMessageBuilder:
    """Test cases for SlackMessageBuilder class."""

    def test_build_mention_with_user_id(self) -> None:
        """Test building mention with user ID (U12345)."""
        slack_contact = SlackContactInfo(channel="C12345", target="U12345", target_type=SlackTargetType.USER)
        mention = SlackMessageBuilder._build_mention(slack_contact)
        assert mention == "<@U12345>"

    def test_build_mention_with_username(self) -> None:
        """Test building mention with @username."""
        slack_contact = SlackContactInfo(channel="C12345", target="@testuser", target_type=SlackTargetType.USER)
        mention = SlackMessageBuilder._build_mention(slack_contact)
        assert mention == "@testuser"

    def test_build_mention_with_usergroup(self) -> None:
        """Test building mention with usergroup - system wraps group ID in Slack format."""
        slack_contact = SlackContactInfo(channel="C12345", target="S12345", target_type=SlackTargetType.USERGROUP)
        mention = SlackMessageBuilder._build_mention(slack_contact)
        assert mention == "<!subteam^S12345>"

    def test_build_mention_with_fallback(self) -> None:
        """Test building mention with non-standard format (fallback)."""
        slack_contact = SlackContactInfo(channel="C12345", target="testuser", target_type=SlackTargetType.USER)
        mention = SlackMessageBuilder._build_mention(slack_contact)
        assert mention == "<testuser>"

    def test_build_request_sent_blocks_approval(self) -> None:
        """Test building blocks for REQUEST_SENT notification (Approval use case)."""
        slack_contact = SlackContactInfo(channel="C12345", target="@testuser", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-31 12:00:00 UTC",
            temporary_link="https://example.com/approval/sess-456.html",
            message="Do you approve deploying to production?",
        )

        blocks = SlackMessageBuilder._build_request_sent_blocks(data, slack_contact)

        # Should have 4 blocks: greeting, quoted message, details, actions
        assert len(blocks) == 4

        # First block: greeting
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"
        assert "@testuser" in blocks[0]["text"]["text"]
        assert "NovaAct" in blocks[0]["text"]["text"]

        # Second block: quoted message
        assert blocks[1]["type"] == "section"
        assert blocks[1]["text"]["type"] == "mrkdwn"
        assert "> Do you approve deploying to production?" == blocks[1]["text"]["text"]

        # Third block: details - should contain approval-specific message
        assert blocks[2]["type"] == "section"
        assert blocks[2]["text"]["type"] == "mrkdwn"
        assert "designated approver" in blocks[2]["text"]["text"]
        assert "approve or deny" in blocks[2]["text"]["text"]
        assert "2025-10-31 12:00:00 UTC" in blocks[2]["text"]["text"]
        assert "wf-123" in blocks[2]["text"]["text"]
        assert "sess-456" in blocks[2]["text"]["text"]
        assert "act-789" in blocks[2]["text"]["text"]

        # Fourth block: action button
        assert blocks[3]["type"] == "actions"
        assert len(blocks[3]["elements"]) == 1
        assert blocks[3]["elements"][0]["type"] == "button"
        assert blocks[3]["elements"][0]["text"]["text"] == "Review Request"
        assert blocks[3]["elements"][0]["url"] == "https://example.com/approval/sess-456.html"

    def test_build_request_sent_blocks_ui_takeover(self) -> None:
        """Test building blocks for REQUEST_SENT notification (UI Takeover use case)."""
        slack_contact = SlackContactInfo(channel="C12345", target="U98765", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-999",
            session_id="sess-888",
            act_id="act-777",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-11-01 14:30:00 UTC",
            temporary_link="https://example.com/browser/sess-888.html",
            message="Browser session needs human intervention",
        )

        blocks = SlackMessageBuilder._build_request_sent_blocks(data, slack_contact)

        # Should have 4 blocks: greeting, quoted message, details, actions
        assert len(blocks) == 4

        # First block: greeting
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"
        assert "<@U98765>" in blocks[0]["text"]["text"]
        assert "NovaAct" in blocks[0]["text"]["text"]

        # Second block: quoted message
        assert blocks[1]["type"] == "section"
        assert blocks[1]["text"]["type"] == "mrkdwn"
        assert "> Browser session needs human intervention" == blocks[1]["text"]["text"]

        # Third block: details - should contain UI takeover-specific message
        assert blocks[2]["type"] == "section"
        assert blocks[2]["text"]["type"] == "mrkdwn"
        assert "connect to the session" in blocks[2]["text"]["text"]
        assert "takeover the browser" in blocks[2]["text"]["text"]
        assert "help complete task" in blocks[2]["text"]["text"]
        assert "2025-11-01 14:30:00 UTC" in blocks[2]["text"]["text"]
        assert "wf-999" in blocks[2]["text"]["text"]
        assert "sess-888" in blocks[2]["text"]["text"]
        assert "act-777" in blocks[2]["text"]["text"]

        # Fourth block: action button
        assert blocks[3]["type"] == "actions"
        assert len(blocks[3]["elements"]) == 1
        assert blocks[3]["elements"][0]["type"] == "button"
        assert blocks[3]["elements"][0]["text"]["text"] == "Review Request"
        assert blocks[3]["elements"][0]["url"] == "https://example.com/browser/sess-888.html"

    def test_build_expiration_blocks(self) -> None:
        """Test building blocks for REQUEST_EXPIRED notification."""
        slack_contact = SlackContactInfo(channel="C12345", target="U54321", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Request expired",
        )

        blocks = SlackMessageBuilder._build_expiration_blocks(data, slack_contact)

        # Should have 1 block
        assert len(blocks) == 1

        # Block should be mrkdwn section
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

        # Should contain user mention
        assert "<@U54321>" in blocks[0]["text"]["text"]

        # Should contain expiration message
        assert "expired" in blocks[0]["text"]["text"].lower()
        assert "stop" in blocks[0]["text"]["text"].lower()

    def test_build_success_completion_blocks_for_approved(self) -> None:
        """Test building blocks for REQUEST_APPROVED notification."""
        slack_contact = SlackContactInfo(channel="C12345", target="@approver", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Request approved",
        )

        blocks = SlackMessageBuilder._build_success_completion_blocks(data, slack_contact)

        # Should have 1 block
        assert len(blocks) == 1

        # Block should be mrkdwn section
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

        # Should contain user mention
        assert "@approver" in blocks[0]["text"]["text"]

        # Should contain success message
        assert "Thanks for responding" in blocks[0]["text"]["text"]
        assert "complete" in blocks[0]["text"]["text"].lower()

    def test_build_success_completion_blocks_for_completed(self) -> None:
        """Test building blocks for REQUEST_COMPLETED notification."""
        slack_contact = SlackContactInfo(channel="C12345", target="U11111", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_COMPLETED,
            message="Task completed",
        )

        blocks = SlackMessageBuilder._build_success_completion_blocks(data, slack_contact)

        # Should have 1 block
        assert len(blocks) == 1

        # Block should be mrkdwn section
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

        # Should contain user mention
        assert "<@U11111>" in blocks[0]["text"]["text"]

        # Should contain completion message
        assert "Thanks for responding" in blocks[0]["text"]["text"]

    def test_build_termination_blocks_for_denied(self) -> None:
        """Test building blocks for REQUEST_DENIED notification."""
        slack_contact = SlackContactInfo(channel="C12345", target="@denier", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_DENIED,
            message="Request denied",
        )

        blocks = SlackMessageBuilder._build_termination_blocks(data, slack_contact)

        # Should have 1 block
        assert len(blocks) == 1

        # Block should be mrkdwn section
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

        # Should contain user mention
        assert "@denier" in blocks[0]["text"]["text"]

        # Should contain termination message
        assert "Thanks for responding" in blocks[0]["text"]["text"]
        assert "stop" in blocks[0]["text"]["text"].lower()

    def test_build_termination_blocks_for_terminated(self) -> None:
        """Test building blocks for REQUEST_TERMINATED notification."""
        slack_contact = SlackContactInfo(channel="C12345", target="U22222", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_TERMINATED,
            message="Request terminated",
        )

        blocks = SlackMessageBuilder._build_termination_blocks(data, slack_contact)

        # Should have 1 block
        assert len(blocks) == 1

        # Block should be mrkdwn section
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

        # Should contain user mention
        assert "<@U22222>" in blocks[0]["text"]["text"]

        # Should contain termination message
        assert "workflow will now stop" in blocks[0]["text"]["text"]

    def test_build_blocks_dispatches_request_sent(self) -> None:
        """Test build_blocks dispatcher for REQUEST_SENT."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-31 12:00:00 UTC",
            temporary_link="https://example.com/link",
            message="Test message",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_SENT should have 4 blocks
        assert len(blocks) == 4
        assert blocks[3]["type"] == "actions"  # Has action buttons

    def test_build_blocks_dispatches_request_expired(self) -> None:
        """Test build_blocks dispatcher for REQUEST_EXPIRED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Request expired",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_EXPIRED should have 1 block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"

    def test_build_blocks_dispatches_request_approved(self) -> None:
        """Test build_blocks dispatcher for REQUEST_APPROVED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Request approved",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_APPROVED should have 1 block
        assert len(blocks) == 1
        assert "Thanks for responding" in blocks[0]["text"]["text"]

    def test_build_blocks_dispatches_request_denied(self) -> None:
        """Test build_blocks dispatcher for REQUEST_DENIED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_DENIED,
            message="Request denied",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_DENIED should have 1 block
        assert len(blocks) == 1
        assert "stop" in blocks[0]["text"]["text"].lower()

    def test_build_blocks_dispatches_request_completed(self) -> None:
        """Test build_blocks dispatcher for REQUEST_COMPLETED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_COMPLETED,
            message="Task completed",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_COMPLETED should have 1 block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert "Thanks for responding" in blocks[0]["text"]["text"]
        assert "complete" in blocks[0]["text"]["text"].lower()

    def test_build_blocks_dispatches_request_terminated(self) -> None:
        """Test build_blocks dispatcher for REQUEST_TERMINATED."""
        slack_contact = SlackContactInfo(channel="C12345", target="U33333", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_TERMINATED,
            message="Request terminated",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_TERMINATED should have 1 block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert "<@U33333>" in blocks[0]["text"]["text"]
        assert "stop" in blocks[0]["text"]["text"].lower()

    def test_build_blocks_dispatches_request_sent_ui_takeover(self) -> None:
        """Test build_blocks dispatcher for REQUEST_SENT with UI_TAKEOVER use case."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-31 12:00:00 UTC",
            temporary_link="https://example.com/browser/link",
            message="Browser needs help",
        )

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # REQUEST_SENT should have 4 blocks
        assert len(blocks) == 4
        assert blocks[3]["type"] == "actions"  # Has action buttons
        # Verify UI takeover specific message
        assert "connect to the session" in blocks[2]["text"]["text"]
        assert "takeover the browser" in blocks[2]["text"]["text"]

    def test_build_blocks_unknown_notification_type(self) -> None:
        """Test build_blocks with unknown notification type uses fallback."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        # Create a NotificationData with a mocked unknown type (for testing fallback)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,  # Valid type for construction
            message="Fallback message test",
        )

        # Temporarily override the notification_type to simulate unknown type
        # This tests the else branch in build_blocks
        data.notification_type = "UNKNOWN_TYPE"  # type: ignore

        blocks = SlackMessageBuilder.build_blocks(data, slack_contact)

        # Fallback should return simple section block with message
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"
        assert blocks[0]["text"]["text"] == "Fallback message test"

    def test_get_fallback_text_request_sent(self) -> None:
        """Test fallback text for REQUEST_SENT."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            message="Approve this deployment",
            temporary_link="https://example.com/link",
            expiration_time_utc="2025-10-31 12:00:00 UTC",
        )

        fallback = SlackMessageBuilder.get_fallback_text(data)

        assert "NovaAct approval request" in fallback
        assert "Approve this deployment" in fallback

    def test_get_fallback_text_request_expired(self) -> None:
        """Test fallback text for REQUEST_EXPIRED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_EXPIRED,
            message="Request expired",
        )

        fallback = SlackMessageBuilder.get_fallback_text(data)

        assert fallback == "Request expired"

    def test_get_fallback_text_request_approved(self) -> None:
        """Test fallback text for REQUEST_APPROVED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_APPROVED,
            message="Request approved",
        )

        fallback = SlackMessageBuilder.get_fallback_text(data)

        assert fallback == "Request approved"

    def test_get_fallback_text_request_denied(self) -> None:
        """Test fallback text for REQUEST_DENIED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_DENIED,
            message="Request denied",
        )

        fallback = SlackMessageBuilder.get_fallback_text(data)

        assert fallback == "Request denied"

    def test_get_fallback_text_request_terminated(self) -> None:
        """Test fallback text for REQUEST_TERMINATED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_TERMINATED,
            message="Request terminated",
        )

        fallback = SlackMessageBuilder.get_fallback_text(data)

        assert fallback == "Request terminated"

    def test_get_fallback_text_request_completed(self) -> None:
        """Test fallback text for REQUEST_COMPLETED."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_COMPLETED,
            message="Task completed",
        )

        fallback = SlackMessageBuilder.get_fallback_text(data)

        assert fallback == "Task completed"

    def test_get_fallback_text_unknown_type(self) -> None:
        """Test fallback text for unknown notification type."""
        slack_contact = SlackContactInfo(channel="C12345", target="@user", target_type=SlackTargetType.USER)
        data = NotificationData(
            recipients=[slack_contact],
            workflow_run_id="wf-123",
            session_id="sess-456",
            act_id="act-789",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            message="Unknown type message",
        )

        # Override to unknown type
        data.notification_type = "UNKNOWN"  # type: ignore

        fallback = SlackMessageBuilder.get_fallback_text(data)

        # Should return the message field
        assert fallback == "Unknown type message"
