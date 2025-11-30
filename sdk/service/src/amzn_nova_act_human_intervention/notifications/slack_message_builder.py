"""Slack message builder for generating Block Kit formatted messages.

This module provides SlackMessageBuilder that generates rich text formatted
messages matching the Slack Workflow configurations for all notification types.
"""

from typing import List

from amzn_nova_act_human_intervention_common import (
    GenericDict,
    LoggingConfig,
    SlackContactInfo,
    SlackTargetType,
    UseCase,
)

from amzn_nova_act_human_intervention.notifications import NotificationData, NotificationType

logger = LoggingConfig.get_logger(__name__)


class SlackMessageBuilder:
    """Builder for creating Slack Block Kit messages.

    This class handles the generation of formatted Slack messages for all
    notification types using mrkdwn format for consistent user mention support.

    All messages use mrkdwn section blocks to support:
    - User mentions with @username or user IDs
    - Usergroup mentions
    - Rich formatting (bold, code, etc.)

    Message format groupings:
    - REQUEST_SENT: Section blocks with mrkdwn, quote, and action buttons
    - REQUEST_EXPIRED: Section block with mrkdwn text
    - REQUEST_APPROVED + REQUEST_COMPLETED: Section block with success message
    - REQUEST_TERMINATED + REQUEST_DENIED: Section block with termination message
    """

    @staticmethod
    def build_blocks(data: NotificationData, slack_contact: SlackContactInfo) -> List[GenericDict]:
        """Build Slack blocks based on notification type.

        Args:
            data: Notification data
            slack_contact: Slack contact information with channel and target

        Returns:
            List of Slack block dictionaries
        """
        if data.notification_type == NotificationType.REQUEST_SENT:
            return SlackMessageBuilder._build_request_sent_blocks(data, slack_contact)
        elif data.notification_type == NotificationType.REQUEST_EXPIRED:
            return SlackMessageBuilder._build_expiration_blocks(data, slack_contact)
        elif data.notification_type in [NotificationType.REQUEST_APPROVED, NotificationType.REQUEST_COMPLETED]:
            return SlackMessageBuilder._build_success_completion_blocks(data, slack_contact)
        elif data.notification_type in [NotificationType.REQUEST_TERMINATED, NotificationType.REQUEST_DENIED]:
            return SlackMessageBuilder._build_termination_blocks(data, slack_contact)
        else:
            # Fallback: simple text block
            logger.warning(f"Unknown notification type: {data.notification_type}, using fallback format")
            return [{"type": "section", "text": {"type": "mrkdwn", "text": data.message}}]

    @staticmethod
    def get_fallback_text(data: NotificationData) -> str:
        """Get fallback text for notification.

        Args:
            data: Notification data

        Returns:
            Fallback text string
        """
        if data.notification_type == NotificationType.REQUEST_SENT:
            return f"NovaAct approval request: {data.message}"
        elif data.notification_type == NotificationType.REQUEST_EXPIRED:
            return "Request expired"
        elif data.notification_type == NotificationType.REQUEST_APPROVED:
            return "Request approved"
        elif data.notification_type == NotificationType.REQUEST_DENIED:
            return "Request denied"
        elif data.notification_type == NotificationType.REQUEST_TERMINATED:
            return "Request terminated"
        elif data.notification_type == NotificationType.REQUEST_COMPLETED:
            return "Task completed"
        else:
            return data.message

    @staticmethod
    def _build_mention(slack_contact: SlackContactInfo) -> str:
        """Build a Slack mention string for mrkdwn blocks.

        Handles formatting for both users and usergroups:
        - For usergroups: Wraps the group ID (e.g., "S12345") in Slack's subteam format
        - For users: Formats user IDs or keeps @username as-is

        Args:
            slack_contact: Slack contact information
                - For usergroups: target should be just the group ID (e.g., "S12345")
                - For users: target can be "@username" or user ID (e.g., "U12345")

        Returns:
            Formatted mention string:
            - Usergroup: "<!subteam^S12345>"
            - User ID: "<@U12345>"
            - Username: "@username"
        """
        if slack_contact.target_type == SlackTargetType.USERGROUP:
            # Wrap group ID in Slack's subteam mention format
            return f"<!subteam^{slack_contact.target}>"

        # User mention - check if it's already a user ID or @username
        if slack_contact.target.startswith("U"):
            # User ID - format as <@U12345>
            return f"<@{slack_contact.target}>"
        elif slack_contact.target.startswith("@"):
            # @username - keep as is
            return slack_contact.target
        else:
            # Fallback - wrap in <>
            return f"<{slack_contact.target}>"

    @staticmethod
    def _build_request_sent_blocks(data: NotificationData, slack_contact: SlackContactInfo) -> List[GenericDict]:
        """Build Slack Block Kit blocks for initial request notification.

        Matches the format from Slack Workflow: "Nova Act Request Pending Human Approval"

        Format:
        - Section: "Hi @user, NovaAct needs your help..."
        - Section: Quote block with message
        - Section: Details (expiration, IDs)
        - Actions: Acknowledge and Review Request buttons
        """
        mention = SlackMessageBuilder._build_mention(slack_contact)

        if data.use_case == UseCase.UI_TAKEOVER:
            message_start = (
                "You can click the request link below to connect to the session, "
                "takeover the browser and help complete task"
            )
        else:
            message_start = (
                "As the designated approver, you need to review the information and either approve or deny the request."
            )

        blocks: List[GenericDict] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Hi {mention},\n\n`NovaAct` needs your help review the following:",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"> {data.message}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{message_start}\n\n"
                        f"The link will expire at `{data.expiration_time_utc}`\n"
                        f"Workflow Run ID: `{data.workflow_run_id}`\n"
                        f"Session ID: `{data.session_id}`\n"
                        f"Act ID: `{data.act_id}`"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review Request", "emoji": True},
                        "style": "primary",
                        "url": data.temporary_link,
                        "action_id": "review_request_button",
                    },
                ],
            },
        ]

        return blocks

    @staticmethod
    def _build_expiration_blocks(data: NotificationData, slack_contact: SlackContactInfo) -> List[GenericDict]:
        """Build Slack Block Kit blocks for expiration notification.

        Format: "Hi @user, The request has expired..."

        Uses mrkdwn format for consistent user mention support.
        """
        mention = SlackMessageBuilder._build_mention(slack_contact)

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hi {mention},\n\n"
                        f"The request has expired without a response. "
                        f"Nova Act will now stop the workflow."
                    ),
                },
            }
        ]
        return blocks

    @staticmethod
    def _build_success_completion_blocks(data: NotificationData, slack_contact: SlackContactInfo) -> List[GenericDict]:
        """Build Slack Block Kit blocks for successful completion.

        Used for both REQUEST_APPROVED and REQUEST_COMPLETED.

        Format: "Hi @user, Thanks for responding/completing..."

        Uses mrkdwn format for consistent user mention support.
        """
        mention = SlackMessageBuilder._build_mention(slack_contact)

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hi {mention},\n\n"
                        f"Thanks for responding to the request. "
                        f"Nova Act has successfully recorded your action and the workflow is now complete."
                    ),
                },
            }
        ]
        return blocks

    @staticmethod
    def _build_termination_blocks(data: NotificationData, slack_contact: SlackContactInfo) -> List[GenericDict]:
        """Build Slack Block Kit blocks for termination/denial.

        Used for both REQUEST_TERMINATED and REQUEST_DENIED.

        Format: "Hi @user, Thanks for responding... the workflow will now stop."

        Uses mrkdwn format for consistent user mention support.
        """
        mention = SlackMessageBuilder._build_mention(slack_contact)

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Hi {mention},\n\n"
                        f"Thanks for responding to the request. "
                        f"Nova Act has successfully recorded your action and the workflow will now stop."
                    ),
                },
            }
        ]
        return blocks
