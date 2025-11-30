import html
import json
import os
import time
from typing import Union

from amzn_nova_act_human_intervention_common import (
    ApprovalAction,
    ApprovalStepFunctionInput,
    ExecutionItem,
    ExecutionStatus,
    GenericDict,
    JSONType,
    LoggingConfig,
    StepFunctionInput,
    UITakeoverStepFunctionInput,
)
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.models import ApprovalSPAParams, LambdaResponse
from amzn_nova_act_human_intervention.utils import (
    S3PresignedUrlHandler,
    send_websocket_message,
)
from amzn_nova_act_human_intervention.workflows.base_handlers import BaseWorkflowHandler

logger = LoggingConfig.get_logger(__name__)


class ApprovalWorkflowHandler(BaseWorkflowHandler):
    """Approval workflow handler implementation."""

    def __init__(self) -> None:
        super().__init__()
        # Approval-specific: S3 URL handler for screenshot conversion and cleanup
        self._s3_url_handler = S3PresignedUrlHandler(s3_client=self._s3_client)

    def handle_spa_generator(self, event: GenericDict, context: LambdaContext) -> JSONType:
        """Generate SPA for approval workflow."""
        request: Union[UITakeoverStepFunctionInput, ApprovalStepFunctionInput] = StepFunctionInput.from_payload(event)

        # Type guard: only ApprovalStepFunctionInput for approval workflows
        if not isinstance(request, ApprovalStepFunctionInput):
            raise TypeError("handle_spa_generator only supports ApprovalStepFunctionInput")

        api_base_url = os.environ.get("API_BASE_URL")
        api_path_prefix = os.environ.get("API_PATH_PREFIX")
        if not api_base_url:
            raise ValueError("API_BASE_URL environment variable not set")
        if not api_path_prefix:
            raise ValueError("API_PATH_PREFIX environment variable not set")

        # Generate API URLs for approval workflow
        api_urls = {
            "record_response_url": f"{api_base_url}{api_path_prefix}/record-response",
            "task_status_url": f"{api_base_url}{api_path_prefix}/task-status",
            "terminate_workflow_url": f"{api_base_url}{api_path_prefix}/terminate-workflow",
            "view_details_url": f"{api_base_url}{api_path_prefix}/view-details",
        }

        link_to_spa: str = self._generate_presigned_url_for_spa(event_id=request.event_id, expires_in=request.timeout)

        # Convert presigned URL to data URL for embedding in HTML
        screenshot_data_url = self._s3_url_handler.convert_to_data_url(request.most_recent_screenshot)

        params = ApprovalSPAParams(
            message=request.query,
            options=request.options,
            session_name=request.event_id,
            spa_type=request.type.value,
            api_urls=api_urls,
            timeout=request.timeout,
            workflow_run_id=request.workflow_run_id,
            act_id=request.act_id,
            session_id=request.session_id,
            screenshot=screenshot_data_url,
        )

        spa_content: str = self._generate_spa_content(event_id=request.event_id, params=params)
        self._write_spa_to_s3(event_id=request.event_id, content=spa_content)

        # Delete screenshot from S3 after embedding in SPA
        # Screenshot is no longer needed as it's now part of the HTML as a data URL
        self._s3_url_handler.delete_object(request.most_recent_screenshot)

        # Send notifications after SPA generation and capture Slack response for threading
        slack_response = self._notification_factory.send_spa_url_notification(request, link_to_spa)

        # Update execution status to PENDING_HUMAN_INPUT and notify WebSocket client
        executions_table = self._dynamodb_client.Table(os.environ["EXECUTIONS_TABLE"])

        # Get execution item to retrieve connection details
        response = executions_table.get_item(Key={"eventId": request.event_id})
        if "Item" in response:
            # Update execution status and store thread_ts for threaded notifications
            update_expression = "SET executionStatus = :status, updatedAt = :updated_at"
            expression_values = {
                ":status": ExecutionStatus.PENDING_HUMAN_INPUT.value,
                ":updated_at": int(time.time()),
            }

            # Add thread_ts if available for Slack threading support
            if slack_response and slack_response.get("ts"):
                thread_ts = slack_response["ts"]
                update_expression += ", slackThreadTs = :thread_ts"
                expression_values[":thread_ts"] = thread_ts
                logger.info(f"Stored Slack thread TS for threading: {thread_ts}")
            else:
                logger.warning(
                    f"No valid thread_ts to store for event {request.event_id}. "
                    f"slack_response={slack_response}. Subsequent Slack notifications will not be threaded."
                )

            executions_table.update_item(
                Key={"eventId": request.event_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
            )

            # Send WebSocket notification
            execution_item: ExecutionItem = ExecutionItem(**response["Item"])
            if execution_item.connectionId:
                send_websocket_message(
                    endpoint=execution_item.executionEndpoint,
                    connection_id=execution_item.connectionId,
                    message={
                        "type": "workflow_started",
                        "workflowRunId": request.workflow_run_id,
                        "sessionId": request.session_id,
                        "actId": request.act_id,
                        "eventId": request.event_id,
                        "spaUrl": link_to_spa,
                        "message": "Approval workflow started successfully. "
                        "SPA has been generated and notifications have been sent.",
                    },
                )

        return LambdaResponse.success(
            body={
                "message": "Approval request sent successfully",
                "event_id": request.event_id,
                "notification_sent": slack_response is not None,
                "threaded": slack_response is not None and slack_response.get("ts") is not None,
            }
        ).for_lambda()

    def _generate_presigned_url_for_spa(self, event_id: str, expires_in: int) -> str:
        """Generate CloudFront URL for Approval SPA.

        Args:
            event_id: Unique identifier for the approval request
            expires_in: Number of seconds until URL expires (unused, kept for compatibility)

        Returns:
            CloudFront URL for accessing the SPA
        """
        cloudfront_domain = os.environ.get("SPA_CLOUDFRONT_DOMAIN")
        if not cloudfront_domain:
            raise ValueError("SPA_CLOUDFRONT_DOMAIN environment variable not set")
        url = f"https://{cloudfront_domain}/{event_id}.html"
        logger.info(f"Generated CloudFront URL for SPA: {url}")
        return url

    def _write_spa_to_s3(self, event_id: str, content: str) -> None:
        """Write Approval SPA content to S3.

        Tags the object as temporary so it will be deleted by lifecycle rules after 1 day.
        """
        bucket_name = os.environ.get("SPA_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("SPA_BUCKET_NAME environment variable not set")
        self._s3_client.put_object(
            Bucket=bucket_name,
            Key=f"{event_id}.html",
            Body=content,
            ContentType="text/html",
            CacheControl="no-cache, no-store, must-revalidate",
            Tagging="temporary=true",  # Tag for lifecycle deletion
        )

    def _generate_spa_content(self, event_id: str, params: ApprovalSPAParams) -> str:
        """Create Approval SPA HTML content matching the mockup"""

        question = html.escape(params.message)
        screenshot = params.screenshot or ""

        # Calculate time to expiry
        from datetime import datetime, timedelta

        expiration_time: datetime = datetime.now() + timedelta(seconds=params.timeout)
        expiration_str: str = expiration_time.strftime("%m/%d/%Y %I:%M%p").lower()

        # Get workflow details (already validated by Pydantic)
        workflow_run_id: str = html.escape(params.workflow_run_id)
        act_id: str = html.escape(params.act_id)
        session_id: str = html.escape(params.session_id)

        # Create timestamp for display
        timestamp: str = datetime.now().strftime("%m/%d/%Y %I:%M%p").lower()

        # Generate buttons from options - use action type to determine button style
        buttons_html = []
        for i, option in enumerate(params.options):
            # Use action field to determine button style: APPROVE = approve style, DENY = deny style
            btn_class = "btn-approve" if option.action == ApprovalAction.APPROVE else "btn-deny"
            btn_id = f"option-{i}-btn"
            escaped_label = html.escape(option.label)
            # Pass both label and action to handleDecision (action.value for enum)
            buttons_html.append(
                f'<button id="{btn_id}" class="btn {btn_class}" '
                f"onclick=\"handleDecision('{escaped_label}', '{option.action.value}')\">{escaped_label}</button>"
            )
        buttons_html_str = "\n            ".join(buttons_html)

        # HTML template for Approval SPA - matches Nova Act mockup
        spa_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nova Act Approval Request</title>
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 40px 20px;
            min-height: 100vh;
            background: #f5f5f7;
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }}

        .container {{
            max-width: 920px;
            width: 100%;
            background: white;
            border-radius: 24px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            padding: 48px;
            display: none;
        }}

        .container.show {{
            display: block;
        }}

        .header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 24px;
        }}

        .nova-icon {{
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 28px;
            flex-shrink: 0;
        }}

        .header h1 {{
            margin: 0;
            font-size: 32px;
            font-weight: 600;
            color: #1a1a1a;
        }}

        .description {{
            font-size: 16px;
            line-height: 1.6;
            color: #4a4a4a;
            margin: 0 0 32px 0;
        }}

        .timestamp-section {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 16px;
            border-bottom: 1px solid #e5e5e5;
        }}

        .timestamp {{
            font-size: 14px;
            color: #8a8a8a;
        }}

        .timestamp strong {{
            color: #4a4a4a;
        }}

        .question-section {{
            margin: 24px 0;
            padding: 24px;
            background: #fafafa;
            border-radius: 12px;
            border-left: 4px solid #8b5cf6;
        }}

        .question-text {{
            font-size: 16px;
            line-height: 1.6;
            color: #2a2a2a;
            margin: 0;
        }}

        .screenshot-section {{
            margin: 32px 0;
            text-align: center;
        }}

        .screenshot-container {{
            background: #f5f5f7;
            border-radius: 16px;
            padding: 16px;
            display: inline-block;
            max-width: 100%;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}

        .screenshot-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            display: block;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .screenshot-zoom {{
            cursor: zoom-in;
        }}

        .screenshot-actions {{
            position: relative;
            display: inline-block;
        }}

        .menu-button {{
            position: absolute;
            bottom: 16px;
            right: 16px;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: white;
            border: 1px solid #e5e5e5;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            transition: all 0.2s;
        }}

        .menu-button:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            transform: scale(1.05);
        }}

        .menu-button::before {{
            content: "⋯";
            font-size: 24px;
            color: #6a6a6a;
            transform: rotate(90deg);
        }}

        .menu-dropdown {{
            position: absolute;
            bottom: 48px;
            right: 0;
            background: white;
            border: 1px solid #e5e5e5;
            border-radius: 12px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            width: 320px;
            display: none;
            z-index: 1000;
        }}

        .menu-dropdown.show {{
            display: block;
        }}

        .menu-item {{
            padding: 16px;
            cursor: pointer;
            border-bottom: 1px solid #f0f0f0;
            transition: background 0.2s;
        }}

        .menu-item:last-child {{
            border-bottom: none;
        }}

        .menu-item:hover {{
            background: #f8f9fa;
        }}

        .menu-item-title {{
            font-weight: 600;
            font-size: 15px;
            color: #1a1a1a;
            margin-bottom: 4px;
        }}

        .menu-item-desc {{
            font-size: 13px;
            color: #6a6a6a;
            line-height: 1.4;
        }}

        .confirmation-dialog {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(4px);
            z-index: 9998;
            display: none;
            justify-content: center;
            align-items: center;
        }}

        .confirmation-dialog.show {{
            display: flex;
        }}

        .confirmation-content {{
            background: white;
            border-radius: 24px;
            padding: 40px;
            max-width: 520px;
            margin: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}

        .confirmation-content h2 {{
            margin: 0 0 16px 0;
            font-size: 24px;
            color: #1a1a1a;
        }}

        .confirmation-content p {{
            margin: 0 0 32px 0;
            font-size: 16px;
            color: #4a4a4a;
            line-height: 1.6;
        }}

        .confirmation-buttons {{
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }}

        .details-modal {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(4px);
            z-index: 9997;
            display: none;
            justify-content: center;
            align-items: center;
        }}

        .details-modal.show {{
            display: flex;
        }}

        .details-content {{
            background: white;
            border-radius: 24px;
            padding: 48px;
            max-width: 680px;
            width: 90%;
            margin: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}

        .details-content h2 {{
            margin: 0 0 24px 0;
            font-size: 28px;
            color: #1a1a1a;
        }}

        .details-intro {{
            font-size: 16px;
            color: #4a4a4a;
            line-height: 1.6;
            margin-bottom: 32px;
        }}

        .details-row {{
            display: flex;
            justify-content: space-between;
            padding: 16px 0;
            border-bottom: 1px solid #f0f0f0;
        }}

        .details-row:last-child {{
            border-bottom: none;
        }}

        .details-label {{
            font-weight: 600;
            color: #1a1a1a;
            font-size: 16px;
        }}

        .details-value {{
            color: #4a4a4a;
            font-size: 16px;
            text-align: right;
        }}

        .details-close {{
            margin-top: 32px;
            display: flex;
            justify-content: flex-end;
        }}

        .countdown {{
            font-weight: 600;
            color: #8b5cf6;
        }}

        .action-buttons {{
            display: flex;
            justify-content: flex-end;
            gap: 16px;
            margin-top: 40px;
            padding-top: 32px;
            border-top: 1px solid #e5e5e5;
        }}

        .btn {{
            padding: 14px 32px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            transition: all 0.2s;
            min-width: 140px;
        }}

        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .btn-deny {{
            background: white;
            color: #8b5cf6;
            border: 2px solid #8b5cf6;
        }}

        .btn-deny:hover:not(:disabled) {{
            background: #faf5ff;
        }}

        .btn-approve {{
            background: #8b5cf6;
            color: white;
        }}

        .btn-approve:hover:not(:disabled) {{
            background: #6366f1;
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(139, 92, 246, 0.3);
        }}

        .status-message {{
            padding: 16px 20px;
            border-radius: 12px;
            margin: 20px 0;
            display: none;
            font-size: 15px;
        }}

        .status-message.success {{
            background: #ecfdf5;
            border: 1px solid #86efac;
            color: #166534;
        }}

        .status-message.error {{
            background: #fef2f2;
            border: 1px solid #fca5a5;
            color: #991b1b;
        }}

        .completed-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: #f5f5f7;
            z-index: 9999;
            display: none;
            justify-content: center;
            align-items: center;
        }}

        .completed-content {{
            text-align: center;
            padding: 48px;
            background: white;
            border-radius: 24px;
            max-width: 480px;
            margin: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}

        .completed-content .nova-icon {{
            margin: 0 auto 24px auto;
        }}

        .completed-content h2 {{
            margin: 0 0 16px 0;
            font-size: 28px;
            color: #1a1a1a;
        }}

        .completed-content p {{
            margin: 0;
            font-size: 16px;
            color: #6a6a6a;
            line-height: 1.6;
        }}

        .already-completed {{
            display: flex;
            min-height: 100vh;
            justify-content: center;
            align-items: center;
            padding: 40px 20px;
        }}

        .already-completed.hidden {{
            display: none;
        }}

        .already-completed-card {{
            background: white;
            border-radius: 24px;
            padding: 48px;
            max-width: 680px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
        }}

        .already-completed-card .nova-icon {{
            margin: 0 auto 24px auto;
        }}

        .already-completed-card h1 {{
            margin: 0 0 16px 0;
            font-size: 32px;
            font-weight: 600;
            color: #1a1a1a;
        }}

        .already-completed-card p {{
            margin: 0;
            font-size: 16px;
            color: #6a6a6a;
            line-height: 1.6;
        }}

        /* Image modal for zooming */
        .image-modal {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 10000;
            display: none;
            justify-content: center;
            align-items: center;
            padding: 40px;
            cursor: zoom-out;
        }}

        .image-modal img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 8px;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: 32px 24px;
            }}

            .header h1 {{
                font-size: 24px;
            }}

            .action-buttons {{
                flex-direction: column-reverse;
            }}

            .btn {{
                width: 100%;
            }}
        }}

        .initial-loading-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: #f5f5f7;
            z-index: 10000;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        .initial-loading-overlay.hidden {{
            display: none;
        }}

        .initial-loading-content {{
            text-align: center;
            padding: 48px;
        }}

        .initial-loading-spinner {{
            width: 48px;
            height: 48px;
            border: 4px solid #e5e5e5;
            border-top-color: #8b5cf6;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 24px auto;
        }}

        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}

        .initial-loading-content h2 {{
            margin: 0 0 8px 0;
            font-size: 24px;
            color: #1a1a1a;
        }}

        .initial-loading-content p {{
            margin: 0;
            font-size: 16px;
            color: #6a6a6a;
        }}
    </style>
</head>
<body>
    <!-- Initial Loading Overlay -->
    <div id="initial-loading-overlay" class="initial-loading-overlay">
        <div class="initial-loading-content">
            <div class="initial-loading-spinner"></div>
            <h2>Loading...</h2>
            <p>Please wait while we check the status of this request.</p>
        </div>
    </div>

    <div class="container">
        <!-- Header with Nova icon -->
        <div class="header">
            <div class="nova-icon">✨</div>
            <h1>Nova Act needs your approval!</h1>
        </div>

        <!-- Description -->
        <p class="description">
            Nova Act is helping to complete a task. As the designated approver,
            you need to review the information and either approve or deny the request.
        </p>

        <!-- Timestamp -->
        <div class="timestamp-section">
            <div class="timestamp">
                <strong>Request created:</strong> {timestamp}
            </div>
        </div>

        <!-- Question -->
        <div class="question-section">
            <p class="question-text">{question}</p>
        </div>

        <!-- Screenshot -->
        {
            f'''
        <div class="screenshot-section">
            <div class="screenshot-actions">
                <div class="screenshot-container">
                    <img src="{screenshot}" alt="Screenshot" class="screenshot-zoom"
                        id="screenshot" onclick="openImageModal()">
                </div>
                <div class="menu-button" id="menu-button" onclick="toggleMenu(event)"></div>
                <div class="menu-dropdown" id="menu-dropdown">
                    <div class="menu-item" onclick="showViewDetails()">
                        <div class="menu-item-title">View details</div>
                        <div class="menu-item-desc">
                            View Human in the Loop details like Workflow Run ID, Act ID,
                            Session ID, and detailed HITL request expiration date/time
                        </div>
                    </div>
                    <div class="menu-item" onclick="confirmStopWorkflow()">
                        <div class="menu-item-title">Stop workflow</div>
                        <div class="menu-item-desc">
                            This will force the agent stop the workflow without recording any actions
                        </div>
                    </div>
                </div>
            </div>
        </div>
        '''
            if screenshot
            else ""
        }

        <!-- Status message -->
        <div id="status" class="status-message"></div>

        <!-- Action buttons -->
        <div class="action-buttons">
            {buttons_html_str}
        </div>
    </div>

    <!-- Completion overlay -->
    <div id="completion-overlay" class="completed-overlay">
        <div class="completed-content">
            <div class="nova-icon">✨</div>
            <h2 id="completion-title">Response Recorded</h2>
            <p id="completion-message">Your response has been recorded successfully.</p>
        </div>
    </div>

    <!-- Already completed view -->
    <div id="already-completed" class="already-completed">
        <div class="already-completed-card">
            <div class="nova-icon">✨</div>
            <h1 id="already-completed-title">Loading...</h1>
            <p id="already-completed-message">
                Please wait while we check the status of this request.
            </p>
        </div>
    </div>

    <!-- Image modal for zooming -->
    <div id="image-modal" class="image-modal" onclick="closeImageModal()">
        <img src="{screenshot}" alt="Screenshot zoomed">
    </div>

    <!-- Confirmation dialog for deny -->
    <div id="confirmation-dialog" class="confirmation-dialog">
        <div class="confirmation-content">
            <h2>Are you sure you want to deny the request?</h2>
            <p>Once you deny the request, Nova Act will stop this workflow immediately.</p>
            <div class="confirmation-buttons">
                <button class="btn btn-deny" onclick="closeConfirmation()">Go Back</button>
                <button class="btn btn-approve" onclick="proceedWithDeny()">Yes, Continue</button>
            </div>
        </div>
    </div>

    <!-- Confirmation dialog for stop workflow -->
    <div id="stop-confirmation-dialog" class="confirmation-dialog">
        <div class="confirmation-content">
            <h2>Are you sure you want to stop the workflow?</h2>
            <p>
                After you agree, Nova Act will immediately stop the workflow.
                You will need to contact your administrator to restart the agent
            </p>
            <div class="confirmation-buttons">
                <button class="btn btn-deny" onclick="closeStopConfirmation()">Cancel</button>
                <button class="btn btn-approve" onclick="proceedWithStop()">Agree</button>
            </div>
        </div>
    </div>

    <!-- View details modal -->
    <div id="details-modal" class="details-modal" onclick="closeDetailsModal(event)">
        <div class="details-content" onclick="event.stopPropagation()">
            <h2>About this request</h2>
            <p class="details-intro">
                The request is made from Nova Act following your workflow configurations.
                You can use these information to communicate with your admins to locate the request.
            </p>
            <div id="details-body">
                <!-- Details will be populated here -->
            </div>
            <div class="details-close">
                <button class="btn btn-deny" onclick="closeDetailsModal()">Close</button>
            </div>
        </div>
    </div>

    <script>
        const apiUrls = {json.dumps(params.api_urls, separators=(",", ":"), ensure_ascii=True)};
        const eventId = {json.dumps(event_id)};
        const apiToken = {json.dumps(event_id)};

        function showStatus(message, isError = false) {{
            const statusEl = document.getElementById('status');
            statusEl.textContent = message;
            statusEl.className = 'status-message ' + (isError ? 'error' : 'success');
            statusEl.style.display = 'block';
        }}

        function hideStatus() {{
            document.getElementById('status').style.display = 'none';
        }}

        async function apiCall(url, data = {{}}) {{
            try {{
                const response = await fetch(url, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${{apiToken}}`
                    }},
                    body: JSON.stringify(data)
                }});

                if (!response.ok) {{
                    const errorText = await response.text();
                    console.error('API error response:', errorText);

                    // Handle 409 Conflict with user-friendly message
                    if (response.status === 409) {{
                        try {{
                            const errorData = JSON.parse(errorText);
                            const friendlyMessage = errorData.error || 'This request has already been completed.';
                            throw new Error(friendlyMessage);
                        }} catch (parseError) {{
                            // If JSON parsing fails, use default message
                            throw new Error('This request has already been completed.');
                        }}
                    }}

                    throw new Error(`HTTP ${{response.status}}: ${{response.statusText}}`);
                }}

                return await response.json();
            }} catch (error) {{
                console.error('API call failed:', error);
                throw error;
            }}
        }}

        // Store decision for confirmation dialog
        let pendingDecision = null;

        async function handleDecision(decisionLabel, decisionAction) {{
            // Check if this is a DENY action - show confirmation dialog
            if (decisionAction !== '{ApprovalAction.APPROVE.value}') {{
                pendingDecision = {{ label: decisionLabel, action: decisionAction }};
                document.getElementById('confirmation-dialog').classList.add('show');
                return;
            }}

            // For APPROVE actions, proceed directly
            await recordDecision(decisionAction);
        }}

        async function recordDecision(decisionAction) {{
            const allButtons = document.querySelectorAll('.action-buttons button');

            try {{
                // Disable all buttons
                allButtons.forEach(btn => btn.disabled = true);

                showStatus('Recording your response...');

                const result = await apiCall(apiUrls.record_response_url, {{
                    token: eventId,
                    approvalAction: decisionAction
                }});

                if (result.task_completed) {{
                    showCompletionOverlay(decisionAction);
                }} else {{
                    showStatus(
                        'Failed to record response: ' + (result.error || result.message),
                        true
                    );
                    // Re-enable buttons on error
                    allButtons.forEach(btn => btn.disabled = false);
                }}
            }} catch (error) {{
                showStatus('Error: ' + error.message, true);
                // Re-enable buttons on error
                allButtons.forEach(btn => btn.disabled = false);
            }}
        }}

        function closeConfirmation() {{
            document.getElementById('confirmation-dialog').classList.remove('show');
            pendingDecision = null;
        }}

        async function proceedWithDeny() {{
            const dialog = document.getElementById('confirmation-dialog');
            dialog.classList.remove('show');

            if (pendingDecision) {{
                await recordDecision(pendingDecision.action);
                pendingDecision = null;
            }}
        }}

        // Image zoom functions
        function openImageModal() {{
            document.getElementById('image-modal').style.display = 'flex';
        }}

        function closeImageModal() {{
            document.getElementById('image-modal').style.display = 'none';
        }}

        function showCompletionOverlay(action, errorDetails = null) {{
            const overlay = document.getElementById('completion-overlay');
            const title = document.getElementById('completion-title');
            const message = document.getElementById('completion-message');

            // Use action type to determine the message
            if (action === 'error') {{
                title.textContent = 'Request failed';
                if (errorDetails && errorDetails.message) {{
                    message.innerHTML = errorDetails.message;
                }} else {{
                    message.innerHTML =
                        'An error occurred while processing this request. Please contact your ' +
                        'administrator for more information.<br><br>' +
                        'There\\'s no further action needed.';
                }}
            }} else if (action === '{ApprovalAction.APPROVE.value}') {{
                title.textContent = 'Request Completed!';
                message.textContent =
                    'Thank you! Your decision to approve the request has been recorded. ' +
                    'The Nova Act workflow will now continue.';
            }} else {{
                title.textContent = 'Request Completed!';
                message.textContent =
                    'Thank you! Your decision to deny the request has been recorded. ' +
                    'The Nova Act workflow will now stop.';
            }}

            overlay.style.display = 'flex';
        }}

        // Menu functions
        function toggleMenu(event) {{
            event.stopPropagation();
            const dropdown = document.getElementById('menu-dropdown');
            dropdown.classList.toggle('show');
        }}

        async function showViewDetails() {{
            // Close menu
            document.getElementById('menu-dropdown').classList.remove('show');

            // Populate details modal with workflow information
            const modal = document.getElementById('details-modal');
            const detailsBody = document.getElementById('details-body');

            // Populate details directly from params
            detailsBody.innerHTML = `
                <div class="details-row">
                    <span class="details-label">Workflow Run ID</span>
                    <span class="details-value">{workflow_run_id}</span>
                </div>
                <div class="details-row">
                    <span class="details-label">Act ID</span>
                    <span class="details-value">{act_id}</span>
                </div>
                <div class="details-row">
                    <span class="details-label">Session ID</span>
                    <span class="details-value">{session_id}</span>
                </div>
                <div class="details-row">
                    <span class="details-label">Expiration Time</span>
                    <span class="details-value">{expiration_str}</span>
                </div>
            `;

            modal.classList.add('show');
        }}

        function confirmStopWorkflow() {{
            // Close menu
            document.getElementById('menu-dropdown').classList.remove('show');

            // Show stop confirmation dialog
            document.getElementById('stop-confirmation-dialog').classList.add('show');
        }}

        function closeStopConfirmation() {{
            document.getElementById('stop-confirmation-dialog').classList.remove('show');
        }}

        async function proceedWithStop() {{
            // Close the confirmation dialog
            document.getElementById('stop-confirmation-dialog').classList.remove('show');

            try {{
                const allButtons = document.querySelectorAll('.action-buttons button');
                allButtons.forEach(btn => btn.disabled = true);

                showStatus('Stopping workflow...');

                const result = await apiCall(apiUrls.terminate_workflow_url, {{
                    token: eventId
                }});

                if (result.workflow_terminated) {{
                    const overlay = document.getElementById('completion-overlay');
                    const title = document.getElementById('completion-title');
                    const message = document.getElementById('completion-message');

                    title.textContent = 'Workflow Stopped';
                    message.textContent =
                        'The workflow has been stopped successfully. No actions were recorded.';

                    overlay.style.display = 'flex';
                }} else {{
                    showStatus(
                        'Failed to stop workflow: ' + (result.error || result.message),
                        true
                    );
                    allButtons.forEach(btn => btn.disabled = false);
                }}
            }} catch (error) {{
                showStatus('Error stopping workflow: ' + error.message, true);
                const allButtons = document.querySelectorAll('.action-buttons button');
                allButtons.forEach(btn => btn.disabled = false);
            }}
        }}

        function closeDetailsModal(event) {{
            // Allow closing by clicking backdrop or close button
            if (!event || event.target.id === 'details-modal' ||
                event.target.classList.contains('btn')) {{
                document.getElementById('details-modal').classList.remove('show');
            }}
        }}

        async function checkTaskStatus() {{
            try {{
                const data = await apiCall(apiUrls.task_status_url, {{
                    token: eventId
                }});

                if (data.task_completed) {{
                    if (data.executionStatus === 'FAILED') {{
                        showCompletionOverlay('error', data.errorDetails);
                    }} else {{
                        showAlreadyCompletedView();
                    }}
                    return true;
                }}
            }} catch (error) {{
                console.error('Error checking task status:', error);
            }}
            return false;
        }}

        function showAlreadyCompletedView() {{
            // Update the message
            document.getElementById('already-completed-title').textContent =
                'The Request has been Completed!';
            document.getElementById('already-completed-message').textContent =
                'This approval request has already been completed. Contact your admin to ' +
                'get more information about the request or workflow status.';

            // Already-completed view is visible by default, no need to show it
            // Just ensure container stays hidden
        }}

        // Close menu when clicking outside
        document.addEventListener('click', (event) => {{
            const menu = document.getElementById('menu-dropdown');
            const menuButton = document.getElementById('menu-button');
            if (menu && !menuButton.contains(event.target)) {{
                menu.classList.remove('show');
            }}
        }});

        // Initialize
        document.addEventListener('DOMContentLoaded', async () => {{
            console.log('Approval page loaded');

            // Check if already completed
            const isCompleted = await checkTaskStatus();

            // Hide initial loading overlay
            const initialLoading = document.getElementById('initial-loading-overlay');
            initialLoading.classList.add('hidden');

            // If not completed, show the main container and hide the already-completed view
            if (!isCompleted) {{
                document.getElementById('already-completed').classList.add('hidden');
                document.querySelector('.container').classList.add('show');
            }}
        }});
    </script>
</body>
</html>"""

        return spa_html

    def _get_completion_message_fields(self, execution_item: ExecutionItem) -> dict:
        """Add approval-specific fields to completion message.

        Args:
            execution_item: The execution item from DynamoDB

        Returns:
            Dictionary with approvalAction field
        """
        return {"approvalAction": execution_item.approvalAction}


def spa_generator_handler(event: GenericDict, context: LambdaContext) -> JSONType:
    """Lambda handler for SPA generation."""
    return ApprovalWorkflowHandler().handle_spa_generator(event, context)


def confirm_if_answered(event: GenericDict, context: LambdaContext) -> JSONType:
    """Lambda handler for confirmation check."""
    return ApprovalWorkflowHandler().handle_confirm_if_answered(event, context)


@event_source(data_class=EventBridgeEvent)
def completion_handler(event: EventBridgeEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for workflow completion."""
    return ApprovalWorkflowHandler().handle_completion(event, context)
