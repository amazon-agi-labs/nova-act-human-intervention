import os
from typing import List

import boto3
from amzn_nova_act_human_intervention_common import EmailContactInfo, LoggingConfig, UseCase

from amzn_nova_act_human_intervention.notifications.base import BaseNotifier, NotificationData

logger = LoggingConfig.get_logger(__name__)


class EmailNotifier(BaseNotifier):
    def __init__(self) -> None:
        self.ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION"))

    def send(self, data: NotificationData) -> bool:
        # Extract email addresses from EmailContactInfo objects
        email_recipients: List[str] = []
        from_email = None

        for recipient in data.recipients:
            if isinstance(recipient, EmailContactInfo):
                email_recipients.append(recipient.to_email_address)
                # Use from_email from first recipient (all should have the same sender)
                if from_email is None:
                    from_email = recipient.from_email_address
                elif from_email != recipient.from_email_address:
                    logger.warning(
                        f"Multiple different from_email addresses found. Using first: {from_email}, "
                        f"ignoring: {recipient.from_email_address}"
                    )
            else:
                logger.warning(f"Skipping non-email recipient: {recipient}")

        if not email_recipients:
            # No email recipients to send to - treat as success (similar to SlackNotifier)
            return True

        # Since from_email_address is required in EmailContactInfo, this should never be None
        # if we have email_recipients
        if from_email is None:
            raise ValueError("No from_email found despite having email recipients")

        if data.use_case == UseCase.UI_TAKEOVER:
            subject = "🖥️ Browser Control Session Ready"
            html_body = self._generate_ui_takeover_html(data)
            text_body = self._generate_ui_takeover_text(data)
        else:  # Approval
            subject = "✅ Approval Request"
            html_body = self._generate_approval_html(data)
            text_body = self._generate_approval_text(data)

        self.ses.send_email(
            Source=from_email,
            Destination={"ToAddresses": email_recipients},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Html": {"Data": html_body}, "Text": {"Data": text_body}},
            },
        )
        logger.info(f"Sent email to {len(email_recipients)} recipients from {from_email}")
        return True

    def _generate_ui_takeover_html(self, data: NotificationData) -> str:
        """Generate HTML email body for UI Takeover use case."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Browser Control Session Ready</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
             margin: 0; padding: 0; background-color: #f5f5f7;">
    <div style="max-width: 600px; margin: 40px auto; background: white; border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 40px 30px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 10px;">🖥️</div>
            <h1 style="margin: 0; color: white; font-size: 28px; font-weight: 600;">
                Browser Control Session Ready
            </h1>
            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 16px;">
                A browser session needs your attention
            </p>
        </div>

        <!-- Content -->
        <div style="padding: 40px 30px;">

            <!-- Message/Query Section -->
            <div style="background: #f8f9fa; border-left: 4px solid #667eea; padding: 20px;
                        border-radius: 8px; margin-bottom: 30px;">
                <h3 style="margin: 0 0 10px 0; color: #333; font-size: 16px; font-weight: 600;">
                    Message:
                </h3>
                <p style="margin: 0; color: #666; font-size: 15px; line-height: 1.6;">
                    {data.message}
                </p>
            </div>

            <!-- Call to Action -->
            <p style="color: #333; font-size: 16px; line-height: 1.6; margin: 0 0 25px 0;">
                You can click the button below to connect to the session, take over the browser,
                and help complete the task.
            </p>

            <!-- Action Button -->
            <div style="text-align: center; margin: 35px 0;">
                <a href="{data.temporary_link}"
                   style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                          color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px;
                          font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(102,126,234,0.4);">
                    🔗 Access Browser Control
                </a>
            </div>

            <!-- Session Details -->
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 30px 0;">
                <h3 style="margin: 0 0 15px 0; color: #333; font-size: 14px; font-weight: 600;
                           text-transform: uppercase; letter-spacing: 0.5px;">
                    Session Details
                </h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Workflow Run ID:</td>
                        <td style="padding: 8px 0; color: #333; font-size: 14px; font-family: monospace;">
                            {data.workflow_run_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Session ID:</td>
                        <td style="padding: 8px 0; color: #333; font-size: 14px; font-family: monospace;">
                            {data.session_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Act ID:</td>
                        <td style="padding: 8px 0; color: #333; font-size: 14px; font-family: monospace;">
                            {data.act_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Expires:</td>
                        <td style="padding: 8px 0; color: #d32f2f; font-size: 14px; font-weight: 600;">
                            {data.expiration_time_utc}
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Warning -->
            <div style="background: #fff3cd; border: 1px solid #ffc107; padding: 15px;
                        border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0; color: #856404; font-size: 14px;">
                    ⚠️ <strong>Important:</strong> This link will expire at {data.expiration_time_utc}.
                    Please access it soon to help complete the task.
                </p>
            </div>
        </div>

        <!-- Footer -->
        <div style="background: #f8f9fa; padding: 20px 30px; text-align: center;
                    border-top: 1px solid #e9ecef;">
            <p style="margin: 0; color: #6c757d; font-size: 12px;">
                This is an automated message from Nova Act
            </p>
        </div>
    </div>
</body>
</html>
        """.strip()

    def _generate_approval_html(self, data: NotificationData) -> str:
        """Generate HTML email body for Approval use case."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Approval Request</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
             margin: 0; padding: 0; background-color: #f5f5f7;">
    <div style="max-width: 600px; margin: 40px auto; background: white; border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                    padding: 40px 30px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 10px;">✅</div>
            <h1 style="margin: 0; color: white; font-size: 28px; font-weight: 600;">
                Approval Required
            </h1>
            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 16px;">
                Your approval is needed for a pending action
            </p>
        </div>

        <!-- Content -->
        <div style="padding: 40px 30px;">

            <!-- Query/Request Section -->
            <div style="background: #f0fdf4; border-left: 4px solid #10b981; padding: 20px;
                        border-radius: 8px; margin-bottom: 30px;">
                <h3 style="margin: 0 0 10px 0; color: #065f46; font-size: 16px; font-weight: 600;">
                    Approval Query:
                </h3>
                <p style="margin: 0; color: #047857; font-size: 15px; line-height: 1.6;">
                    {data.message}
                </p>
            </div>

            <!-- Call to Action -->
            <p style="color: #333; font-size: 16px; line-height: 1.6; margin: 0 0 25px 0;">
                As the designated approver, you need to review the information and either approve
                or deny the request.
            </p>

            <!-- Action Button -->
            <div style="text-align: center; margin: 35px 0;">
                <a href="{data.temporary_link}"
                   style="display: inline-block; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                          color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px;
                          font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(17,153,142,0.4);">
                    📋 Review & Approve
                </a>
            </div>

            <!-- Request Details -->
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 30px 0;">
                <h3 style="margin: 0 0 15px 0; color: #333; font-size: 14px; font-weight: 600;
                           text-transform: uppercase; letter-spacing: 0.5px;">
                    Request Details
                </h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Workflow Run ID:</td>
                        <td style="padding: 8px 0; color: #333; font-size: 14px; font-family: monospace;">
                            {data.workflow_run_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Session ID:</td>
                        <td style="padding: 8px 0; color: #333; font-size: 14px; font-family: monospace;">
                            {data.session_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Act ID:</td>
                        <td style="padding: 8px 0; color: #333; font-size: 14px; font-family: monospace;">
                            {data.act_id}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666; font-size: 14px;">Expires:</td>
                        <td style="padding: 8px 0; color: #d32f2f; font-size: 14px; font-weight: 600;">
                            {data.expiration_time_utc}
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Warning -->
            <div style="background: #fff3cd; border: 1px solid #ffc107; padding: 15px;
                        border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0; color: #856404; font-size: 14px;">
                    ⚠️ <strong>Important:</strong> This approval request will expire at
                    {data.expiration_time_utc}. Please review and respond before the deadline.
                </p>
            </div>
        </div>

        <!-- Footer -->
        <div style="background: #f8f9fa; padding: 20px 30px; text-align: center;
                    border-top: 1px solid #e9ecef;">
            <p style="margin: 0; color: #6c757d; font-size: 12px;">
                This is an automated message from Nova Act
            </p>
        </div>
    </div>
</body>
</html>
        """.strip()

    def _generate_ui_takeover_text(self, data: NotificationData) -> str:
        """Generate plain text email body for UI Takeover use case."""
        return f"""
BROWSER CONTROL SESSION READY
==============================

MESSAGE:
{data.message}

You can click the link below to connect to the session, take over the browser,
and help complete the task.

WORKFLOW RUN ID: {data.workflow_run_id}
SESSION ID: {data.session_id}
ACT ID: {data.act_id}
SECURE ACCESS LINK: {data.temporary_link}
EXPIRES: {data.expiration_time_utc}

⚠️ IMPORTANT: This link will expire at {data.expiration_time_utc}.
Please access it soon to help complete the task.

---
This is an automated message from Nova Act
        """.strip()

    def _generate_approval_text(self, data: NotificationData) -> str:
        """Generate plain text email body for Approval use case."""
        return f"""
APPROVAL REQUIRED
=================

APPROVAL QUERY:
{data.message}

As the designated approver, you need to review the information and either approve
or deny the request.

WORKFLOW RUN ID: {data.workflow_run_id}
SESSION ID: {data.session_id}
ACT ID: {data.act_id}
SECURE ACCESS LINK: {data.temporary_link}
EXPIRES: {data.expiration_time_utc}

⚠️ IMPORTANT: This approval request will expire at {data.expiration_time_utc}.
Please review and respond before the deadline.

---
This is an automated message from Nova Act
        """.strip()
