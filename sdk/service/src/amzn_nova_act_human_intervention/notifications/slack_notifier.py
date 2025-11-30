"""Slack notifier using Slack App (Bot SDK) for sending notifications.

This module provides SlackNotifier that uses the Slack Bot SDK to send
notifications. Message formatting is handled by SlackMessageBuilder.
"""

import json
import os

import boto3
from amzn_nova_act_human_intervention_common import GenericDict, LoggingConfig, SlackContactInfo, UseCase
from slack_sdk import WebClient
from slack_sdk.web import SlackResponse

from amzn_nova_act_human_intervention.notifications.base import BaseNotifier, NotificationData
from amzn_nova_act_human_intervention.notifications.slack_message_builder import SlackMessageBuilder

logger = LoggingConfig.get_logger(__name__)


class SlackNotifier(BaseNotifier):
    """SlackNotifier - Sends notifications to Slack using Slack Bot SDK.

    This notifier uses the Slack Bot SDK (slack_sdk) to send formatted notifications
    with threading support. Message formatting is delegated to SlackMessageBuilder.

    Configuration:
        - Reads from SLACK_SECRETS environment variable pointing to Secrets Manager
        - The secret should contain JSON with use case keys:
          {
            "UITakeover": "xoxb-...",
            "Approval": "xoxb-..."
          }
        - Both fields can have the same token if using a shared bot across use cases

        Required OAuth scopes for the Slack bot:
        - chat:write
        - chat:write.public
    """

    def __init__(self) -> None:
        """Initialize Slack App notifier.

        Reads bot tokens from AWS Secrets Manager using the SLACK_SECRETS environment variable.

        Raises:
            ValueError: If SLACK_SECRETS is not set or cannot retrieve tokens from Secrets Manager
        """
        # Store tokens per use case (UITakeover, Approval)
        self.bot_tokens: GenericDict = {}

        # Read from Secrets Manager
        secret_name = os.environ.get("SLACK_SECRETS")
        if not secret_name:
            raise ValueError("SLACK_SECRETS environment variable must be set")

        try:
            secrets_client = boto3.client("secretsmanager")
            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret_data: GenericDict = json.loads(response["SecretString"])

            # Read tokens for each use case
            for use_case in [UseCase.UI_TAKEOVER.value, UseCase.APPROVAL.value]:
                token = secret_data.get(use_case)
                if token:
                    self.bot_tokens[use_case] = token
                else:
                    logger.warning(f"No bot token found for use case '{use_case}' in secret '{secret_name}'")

            if not self.bot_tokens:
                raise ValueError(f"Secret '{secret_name}' does not contain any valid bot tokens")

            logger.info(
                f"Successfully retrieved Slack bot tokens from Secrets Manager for use cases: "
                f"{list(self.bot_tokens.keys())}"
            )
        except Exception as e:
            logger.error(f"Failed to retrieve Slack bot tokens from Secrets Manager: {e}")
            raise ValueError(f"Failed to retrieve Slack bot tokens from Secrets Manager: {e}") from e

        self.message_builder = SlackMessageBuilder()
        logger.info("SlackNotifier initialized successfully with Slack Bot SDK")

    def _get_slack_client(self, use_case: UseCase) -> WebClient:
        """Get Slack WebClient for the specified use case.

        Args:
            use_case: The use case (UI_TAKEOVER or APPROVAL)

        Returns:
            WebClient configured with the appropriate bot token

        Raises:
            ValueError: If no bot token is available for the use case
        """
        token = self.bot_tokens.get(use_case.value)
        if not token:
            raise ValueError(f"No Slack bot token available for use case: {use_case.value}")
        return WebClient(token=token)

    def send(self, data: NotificationData) -> bool:
        """Send Slack notification using Slack Bot SDK.

        Args:
            data: Notification data containing recipients, message, and metadata

        Returns:
            True if all notifications sent successfully, False otherwise

        Example:
            >>> from amzn_nova_act_human_intervention_common import SlackContactInfo, UseCase
            >>> from amzn_nova_act_human_intervention.notifications.base import NotificationData, NotificationType
            >>> notifier = SlackNotifier()
            >>> data = NotificationData(
            ...     recipients=[SlackContactInfo(channel="C12345", target="@username")],
            ...     workflow_run_id="550e8400-e29b-41d4-a716-446655440000",
            ...     session_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
            ...     act_id="abcdef12-3456-7890-abcd-ef1234567890",
            ...     use_case=UseCase.UI_TAKEOVER,
            ...     notification_type=NotificationType.REQUEST_SENT,
            ...     message="Please complete the reCAPTCHA"
            ... )
            >>> success = notifier.send(data)
            >>> success
            True
        """
        success_count = 0

        for recipient in data.recipients:
            if isinstance(recipient, SlackContactInfo):
                try:
                    # send_message returns SlackThreadInfo for new messages, None for threaded replies
                    # Both indicate success - only exceptions indicate failure
                    self.send_message(data, recipient)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send Slack message to {recipient.channel}: {e}")
            else:
                logger.warning(f"Skipping non-Slack recipient: {recipient}")

        return success_count == len([r for r in data.recipients if isinstance(r, SlackContactInfo)])

    def send_message(self, data: NotificationData, slack_contact: SlackContactInfo) -> SlackResponse | None:
        """Send a single message and return response metadata.

        Args:
            data: Notification data
            slack_contact: Slack contact information with channel and target
                          Note: slack_contact.target can be a username (e.g., "@username")
                          or a user ID (e.g., "U12345"). Both formats work for mentions.

        Returns:
            SlackResponse from Slack SDK if message sent as a new message,
            None if sent as a threaded reply (no need to capture thread info again)
        """
        # Get the appropriate Slack client for this use case
        slack_client = self._get_slack_client(data.use_case)

        # Use SlackMessageBuilder to generate blocks and fallback text
        blocks = self.message_builder.build_blocks(data, slack_contact)
        fallback_text = self.message_builder.get_fallback_text(data)

        # Send as threaded reply if thread_ts available
        if data.slack_thread_identifier:
            slack_client.chat_postMessage(
                channel=slack_contact.channel,
                text=fallback_text,
                blocks=blocks,
                thread_ts=data.slack_thread_identifier,
            ).validate()  # type: ignore[no-untyped-call]
            logger.info(
                f"Sent threaded notification to {slack_contact.channel} in thread {data.slack_thread_identifier}"
            )
            # Return None for threaded replies (no need to capture thread_ts again)
            return None

        response: SlackResponse = slack_client.chat_postMessage(
            channel=slack_contact.channel,
            text=fallback_text,
            blocks=blocks,
        ).validate()  # type: ignore[no-untyped-call]
        logger.info(f"Sent notification to {slack_contact.channel}")
        logger.info(f"   Message TS: {response['ts']}")
        logger.info(f"   Notification Type: {data.notification_type.value}")
        logger.info(f"   Workflow Run ID: {data.workflow_run_id}")

        # Return SlackResponse for new messages to enable threading
        return response
