"""Factory for creating and sending notifications for both UI Takeover and Approval use cases."""

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Set

from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalStepFunctionInput,
    ExecutionItem,
    GenericDict,
    InterventionRequest,
    JSONType,
    LoggingConfig,
    NotificationChannel,
    NotificationRecipient,
    UITakeoverStepFunctionInput,
)
from slack_sdk.web import SlackResponse

from amzn_nova_act_human_intervention.notifications.base import NotificationData, NotificationType
from amzn_nova_act_human_intervention.notifications.email_notifier import EmailNotifier
from amzn_nova_act_human_intervention.notifications.exceptions import NotificationDeliveryError
from amzn_nova_act_human_intervention.notifications.slack_notifier import SlackNotifier

logger = LoggingConfig.get_logger(__name__)


class NotificationFactory:
    """Factory class for creating and sending notifications."""

    def __init__(self) -> None:
        supported_channels_raw: JSONType = json.loads(os.environ.get("SUPPORTED_NOTIFICATION_CHANNELS", "[]"))

        if not isinstance(supported_channels_raw, list) or not supported_channels_raw:
            raise ValueError("SUPPORTED_NOTIFICATION_CHANNELS must be a non-empty list")
        supported_channels: Set[NotificationChannel] = {
            NotificationChannel(channel) for channel in supported_channels_raw
        }

        self.email_notifier: EmailNotifier | None = None
        self.slack_notifier: SlackNotifier | None = None

        if NotificationChannel.EMAIL in supported_channels:
            self.email_notifier = EmailNotifier()

        if NotificationChannel.SLACK in supported_channels:
            # Initialize SlackNotifier (Slack Bot SDK)
            # SlackNotifier will read bot token from SLACK_SECRETS in Secrets Manager
            try:
                self.slack_notifier = SlackNotifier()
                logger.info("SlackNotifier initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize SlackNotifier: {e}")
                raise e

    def send_spa_url_notification(self, request: InterventionRequest, temporary_link: str) -> SlackResponse | None:
        """Send notification when SPA URL is generated (Case 1 - both workflows).

        Both Email and Slack notifications are sent for this case.

        Args:
            request: Intervention request containing workflow details and recipients
            temporary_link: The SPA URL to send to recipients

        Returns:
            SlackResponse from Slack SDK if Slack notification sent successfully,
            None otherwise. The response contains 'ts' and 'channel' fields that can be used
            for subsequent threaded notifications.

        Raises:
            NotificationDeliveryError: If notification delivery fails for any channel

        Example:
            >>> from amzn_nova_act_human_intervention_common import UITakeoverStepFunctionInput
            >>> factory = NotificationFactory()
            >>> request = UITakeoverStepFunctionInput(...)
            >>> slack_response = factory.send_spa_url_notification(
            ...     request=request,
            ...     temporary_link="https://example.com/spa/12345"
            ... )
            >>> slack_response['ts']  # thread timestamp
            '1234567890.123456'
        """
        expiration_time_utc = self._calculate_expiration_time(request.timeout)
        message = self._get_spa_message(request)

        recipients_by_channel = self._group_recipients_by_channel(request.notification_recipients)

        slack_response: SlackResponse | None = None
        failed_channels: List[str] = []

        for channel, recipient_objs in recipients_by_channel.items():
            notification_data = NotificationData(
                recipients=[r.contact_info for r in recipient_objs],
                workflow_run_id=request.workflow_run_id,
                session_id=request.session_id,
                act_id=request.act_id,
                use_case=request.type,
                notification_type=NotificationType.REQUEST_SENT,
                message=message,
                temporary_link=temporary_link,
                expiration_time_utc=expiration_time_utc,
            )

            if channel == NotificationChannel.EMAIL and self.email_notifier:
                try:
                    self.email_notifier.send(notification_data)
                except Exception as e:
                    logger.error(f"Failed to send email notification: {e}")
                    failed_channels.append(f"EMAIL: {str(e)}")

            elif channel == NotificationChannel.SLACK:
                # Use SlackNotifier to send and capture thread_ts for threading
                if not self.slack_notifier:
                    error_msg = "SlackNotifier not initialized"
                    logger.error(f"{error_msg}, cannot send Slack notification")
                    failed_channels.append(f"SLACK: {error_msg}")
                    continue

                for recipient in recipient_objs:
                    try:
                        # Send message using SlackNotifier (it builds blocks internally)
                        # Returns SlackResponse for new messages, None for threaded replies
                        response = self.slack_notifier.send_message(notification_data, recipient.contact_info)

                        # Capture response from first successful message (if not already captured)
                        if response and not slack_response:
                            slack_response = response
                            logger.info(f"Captured thread_ts for threading: {slack_response['ts']}")
                    except Exception as e:
                        logger.error(f"Failed to send Slack notification: {e}")
                        failed_channels.append(f"SLACK: {str(e)}")

        # Raise error if any notifications failed
        if failed_channels:
            raise NotificationDeliveryError(
                f"Notification delivery failed for channels: {', '.join(failed_channels)}", failed_channels
            )

        return slack_response

    def send_expiration_notification(self, execution_item: ExecutionItem) -> bool:
        """Send notification when request expires (Case 2 - both workflows).

        Only Slack notifications are sent for this case.
        If slackThreadTs is available, the notification will be sent as a threaded reply.
        """
        message = f"{execution_item.interventionType.value} request expired without response"

        recipients = execution_item.get_notification_recipients()
        if not recipients:
            logger.warning(f"No recipients found for expired request {execution_item.eventId}")
            return False

        recipients_by_channel = self._group_recipients_by_channel(recipients)

        success = True
        for channel, recipient_objs in recipients_by_channel.items():
            # Only send Slack notifications for expiration
            if channel == NotificationChannel.SLACK:
                if not self.slack_notifier:
                    logger.error("SlackNotifier not initialized, cannot send Slack notification")
                    return False

                notification_data = NotificationData(
                    recipients=[r.contact_info for r in recipient_objs],
                    workflow_run_id=execution_item.workflowRunId,
                    session_id=execution_item.sessionId,
                    act_id=execution_item.actId,
                    use_case=execution_item.interventionType,
                    notification_type=NotificationType.REQUEST_EXPIRED,
                    message=message,
                    slack_thread_identifier=execution_item.slackThreadTs,  # Include thread_ts for threading
                )

                # SlackNotifier handles block building and threading internally
                if not self.slack_notifier.send(notification_data):
                    success = False

        return success

    def send_approval_response_notification(self, execution_item: ExecutionItem, approval_action: str) -> bool:
        """Send notification for approval response (Cases 3 & 4 - Approval workflow only).

        Only Slack notifications are sent for this case.
        If slackThreadTs is available, the notification will be sent as a threaded reply.

        Args:
            execution_item: The execution item from DynamoDB
            approval_action: The approval action (APPROVE or DENY)
        """
        # Determine notification type based on action
        if approval_action == ApprovalAction.APPROVE.value:
            message = "Approval request was approved"
        elif approval_action == ApprovalAction.DENY.value:
            message = "Approval request was denied"
        else:
            logger.error(f"Unknown approval action: {approval_action}")
            return False

        recipients = execution_item.get_notification_recipients()
        if not recipients:
            logger.warning(f"No recipients found for approval response {execution_item.eventId}")
            return False

        recipients_by_channel = self._group_recipients_by_channel(recipients)

        success = True
        for channel, recipient_objs in recipients_by_channel.items():
            # Only send Slack notifications for approval responses
            if channel == NotificationChannel.SLACK:
                if not self.slack_notifier:
                    logger.error("SlackNotifier not initialized, cannot send Slack notification")
                    return False

                notification_data = NotificationData(
                    recipients=[r.contact_info for r in recipient_objs],
                    workflow_run_id=execution_item.workflowRunId,
                    session_id=execution_item.sessionId,
                    act_id=execution_item.actId,
                    use_case=execution_item.interventionType,
                    notification_type=NotificationType.REQUEST_APPROVED
                    if approval_action == ApprovalAction.APPROVE.value
                    else NotificationType.REQUEST_DENIED,
                    message=message,
                    slack_thread_identifier=execution_item.slackThreadTs,  # Include thread_ts for threading
                )

                # SlackNotifier handles block building and threading internally
                if not self.slack_notifier.send(notification_data):
                    success = False

        return success

    def send_task_completion_notification(self, execution_item: ExecutionItem) -> bool:
        """Send notification when UI Takeover task is completed (Case 3 - UI Takeover only).

        Only Slack notifications are sent for this case.
        If slackThreadTs is available, the notification will be sent as a threaded reply.
        """
        message = "UI Takeover task has been completed"

        recipients = execution_item.get_notification_recipients()
        if not recipients:
            logger.warning(f"No recipients found for task completion {execution_item.eventId}")
            return False

        recipients_by_channel = self._group_recipients_by_channel(recipients)

        success = True
        for channel, recipient_objs in recipients_by_channel.items():
            # Only send Slack notifications for task completion
            if channel == NotificationChannel.SLACK:
                if not self.slack_notifier:
                    logger.error("SlackNotifier not initialized, cannot send Slack notification")
                    return False

                notification_data = NotificationData(
                    recipients=[r.contact_info for r in recipient_objs],
                    workflow_run_id=execution_item.workflowRunId,
                    session_id=execution_item.sessionId,
                    act_id=execution_item.actId,
                    use_case=execution_item.interventionType,
                    notification_type=NotificationType.REQUEST_COMPLETED,
                    message=message,
                    slack_thread_identifier=execution_item.slackThreadTs,  # Include thread_ts for threading
                )

                # SlackNotifier handles block building and threading internally
                if not self.slack_notifier.send(notification_data):
                    success = False

        return success

    def send_termination_notification(self, execution_item: ExecutionItem) -> bool:
        """Send notification when workflow is terminated (both workflows).

        Only Slack notifications are sent for this case.
        If slackThreadTs is available, the notification will be sent as a threaded reply.
        """
        message = f"{execution_item.interventionType.value} workflow was terminated"

        recipients = execution_item.get_notification_recipients()
        if not recipients:
            logger.warning(f"No recipients found for terminated workflow {execution_item.eventId}")
            return False

        recipients_by_channel = self._group_recipients_by_channel(recipients)

        success = True
        for channel, recipient_objs in recipients_by_channel.items():
            # Only send Slack notifications for termination
            if channel == NotificationChannel.SLACK:
                if not self.slack_notifier:
                    logger.error("SlackNotifier not initialized, cannot send Slack notification")
                    return False

                notification_data = NotificationData(
                    recipients=[r.contact_info for r in recipient_objs],
                    workflow_run_id=execution_item.workflowRunId,
                    session_id=execution_item.sessionId,
                    act_id=execution_item.actId,
                    use_case=execution_item.interventionType,
                    notification_type=NotificationType.REQUEST_TERMINATED,
                    message=message,
                    slack_thread_identifier=execution_item.slackThreadTs,  # Include thread_ts for threading
                )

                # SlackNotifier handles block building and threading internally
                if not self.slack_notifier.send(notification_data):
                    success = False

        return success

    def _get_spa_message(self, request: InterventionRequest) -> str:
        """Get message for SPA notification."""
        if isinstance(request, UITakeoverStepFunctionInput):
            return request.message
        elif isinstance(request, ApprovalStepFunctionInput):
            return request.query
        else:
            raise ValueError(f"Unknown request type: {type(request)}")

    def _group_recipients_by_channel(self, recipients: List[NotificationRecipient]) -> GenericDict:
        """Group recipients by their notification channel."""
        grouped: GenericDict = dict()
        for recipient in recipients:
            if recipient.channel not in grouped:
                grouped[recipient.channel] = []
            grouped[recipient.channel].append(recipient)
        return grouped

    @staticmethod
    def _calculate_expiration_time(timeout_seconds: int) -> str:
        """Calculate expiration time in UTC format."""
        current_time = datetime.now(timezone.utc)
        expiration_time = current_time.timestamp() + timeout_seconds
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(expiration_time))
