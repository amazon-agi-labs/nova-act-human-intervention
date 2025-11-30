import html
import json
import os
import time
from typing import Union

from amzn_nova_act_human_intervention_common import (
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

from amzn_nova_act_human_intervention.models import UITakeoverSPAParams
from amzn_nova_act_human_intervention.utils import format_seconds_to_human_readable, send_websocket_message
from amzn_nova_act_human_intervention.workflows.base_handlers import BaseWorkflowHandler

logger = LoggingConfig.get_logger(__name__)


class UITakeoverWorkflowHandler(BaseWorkflowHandler):
    """UI Takeover workflow handler implementation."""

    # UITakeover uses only base class initialization (no workflow-specific resources)

    def handle_spa_generator(self, event: GenericDict, context: LambdaContext) -> JSONType:
        """Generate SPA for UI takeover workflow."""
        request: Union[UITakeoverStepFunctionInput, ApprovalStepFunctionInput] = StepFunctionInput.from_payload(event)

        """
        Example input:
        {
          "workflow_run_id": "550e8400-e29b-41d4-a716-446655440000",
          "session_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
          "act_id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
          "event_id": "e4b232ed-ddc6-40bf-b61f-4e62da0c3f2a",
          "type": "UITakeover",
          "timeout": 3600,
          "notification_recipients": [
            {
              "contact_info": "user@amazon.com",
              "channel": "Email"
            }
          ],
          "message": "Human intervention needed for UI interaction",
          "remote_browser": {
            "session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"
          }
        }
        """

        # Type guard: only UITakeoverStepFunctionInput has remote_browser
        if not isinstance(request, UITakeoverStepFunctionInput):
            raise TypeError("handle_spa_generator only supports UITakeoverStepFunctionInput")

        api_base_url = os.environ.get("API_BASE_URL")
        api_path_prefix = os.environ.get("API_PATH_PREFIX")
        if not api_base_url:
            raise ValueError("API_BASE_URL environment variable not set")
        if not api_path_prefix:
            raise ValueError("API_PATH_PREFIX environment variable not set")

        # Generate simple API URLs for token-based authentication
        # No presigning needed - authentication happens via Authorization header
        api_urls = {
            "browser_session_info_url": f"{api_base_url}{api_path_prefix}/browser-session-info",
            "complete_task_url": f"{api_base_url}{api_path_prefix}/complete-task",
            "task_status_url": f"{api_base_url}{api_path_prefix}/task-status",
            "terminate_workflow_url": f"{api_base_url}{api_path_prefix}/terminate-workflow",
            "view_details_url": f"{api_base_url}{api_path_prefix}/view-details",
            "remote_browser": request.remote_browser.model_dump(),  # Pass as dict for JavaScript
        }

        link_to_spa: str = self._generate_presigned_url_for_spa(event_id=request.event_id, expires_in=request.timeout)

        params = UITakeoverSPAParams(
            message=request.message,
            session_name=request.event_id,
            spa_type=request.type.value,
            remote_browser=request.remote_browser.model_dump(),
            api_urls=api_urls,
            timeout=request.timeout,
            workflow_run_id=request.workflow_run_id,
            act_id=request.act_id,
            session_id=request.session_id,
        )

        spa_content: str = self._generate_spa_content(event_id=request.event_id, params=params)
        self._write_spa_to_s3(event_id=request.event_id, content=spa_content)

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
                        "message": "Workflow started successfully. "
                        "SPA has been generated and notifications have been sent.",
                    },
                )

        return {
            "message": "UI Takeover link sent successfully",
            "event_id": request.event_id,
            "notification_sent": slack_response is not None,
            "spa_url": link_to_spa,
        }

    def _generate_presigned_url_for_spa(self, event_id: str, expires_in: int) -> str:
        """Generate CloudFront URL for UI Takeover SPA.

        Args:
            event_id: Unique identifier for the UI takeover request
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
        """Write UI Takeover SPA content to S3.

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

    def _generate_spa_content(self, event_id: str, params: UITakeoverSPAParams) -> str:
        """Create UI Takeover SPA HTML content with pre-signed API calls"""

        dcv_base_url = os.environ.get("DCV_LIBRARY_BASE_URL")
        if not dcv_base_url:
            raise ValueError("DCV_LIBRARY_BASE_URL environment variable not set")

        # Fallback values if viewport not provided
        dcv_display_width: int = 1475
        dcv_display_height: int = 905

        message_from_nova_act: str = html.escape(params.message)

        # Calculate time to expiry
        from datetime import datetime, timedelta

        expiration_time = datetime.now() + timedelta(seconds=params.timeout)
        expiration_str = expiration_time.strftime("%m/%d/%Y %I:%M%p").lower()

        # Calculate human-readable time to expiry
        time_to_expiry = format_seconds_to_human_readable(params.timeout)

        # Get workflow details (already validated by Pydantic)
        workflow_run_id = html.escape(params.workflow_run_id)
        act_id = html.escape(params.act_id)
        session_id = html.escape(params.session_id)

        # HTML template for new SPA
        spa_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nova Act Screen Takeover</title>
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            background: #f5f5f7;
            display: flex;
            flex-direction: column;
        }}

        .top-banner {{
            display: flex;
            justify-content: center;
            padding: 40px 20px 0 20px;
        }}

        .top-banner-content {{
            background: white;
            border-radius: 16px;
            padding: 16px 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            max-width: 1507px;
            width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 32px;
        }}

        .banner-left {{
            display: flex;
            align-items: center;
            gap: 16px;
            flex: 1;
        }}

        .nova-icon {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
            flex-shrink: 0;
        }}

        .banner-text {{
            font-size: 15px;
            color: #1a1a1a;
            line-height: 1.4;
            margin-right: 40px;
        }}

        .banner-text-label {{
            display: block;
            font-weight: 600;
            margin-bottom: 8px;
        }}

        .banner-text-message {{
            display: block;
            background: #faf5ff;
            padding: 8px 12px;
            border-radius: 8px;
            border-left: 3px solid #8b5cf6;
            margin-bottom: 8px;
            font-weight: 500;
        }}

        .banner-text-instruction {{
            display: block;
            font-size: 14px;
            color: #6a6a6a;
        }}

        .btn {{
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
        }}

        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .btn-stop {{
            background: white;
            color: #8b5cf6;
            border: 2px solid #8b5cf6;
        }}

        .btn-stop:hover:not(:disabled) {{
            background: #faf5ff;
        }}

        .main-container {{
            padding: 20px;
        }}

        .display-wrapper-container {{
            max-width: {dcv_display_width}px;
            margin: 0 auto;
        }}

        #dcv-display-wrapper {{
            max-width: 100vw;
            margin: 0 auto;
            position: relative;
            background: #000;
            border-radius: 16px;
            overflow: hidden;
            max-height: calc(100vh - 300px);
        }}

        #dcv-display {{
            width: 100%;
            height: 100%;
            position: relative;
            background: #000;
        }}

        .control-section {{
            display: flex;
            align-items: center;
            gap: 16px;
            flex-shrink: 0;
            margin-left: auto;
        }}

        .control-text {{
            display: none;
        }}

        .btn-takeover {{
            background: #8b5cf6;
            color: white;
            padding: 12px 28px;
            font-size: 15px;
        }}

        .btn-takeover:hover:not(:disabled) {{
            background: #6366f1;
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(139, 92, 246, 0.3);
        }}

        .info-section {{
            padding: 32px 24px;
            text-align: center;
        }}

        .info-section p {{
            font-size: 15px;
            color: #4a4a4a;
            line-height: 1.6;
            margin: 0 0 8px 0;
        }}

        .info-value {{
            color: #6a6a6a;
            font-weight: normal;
        }}

        .expiration-text {{
            font-size: 14px;
            color: #8a8a8a;
        }}

        .status-message {{
            max-width: 1400px;
            width: 100%;
            margin: 0 auto 16px auto;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 14px;
            display: none;
            text-align: center;
        }}

        .status-message.success {{
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}

        .status-message.error {{
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}

        .menu-container {{
            margin: 20px 0 0 auto;
            width: 48px;
            position: relative;
        }}

        .menu-button {{
            width: 48px;
            height: 48px;
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
            bottom: 100%;
            right: 0;
            margin-bottom: 8px;
            background: white;
            border: 1px solid #e5e5e5;
            border-radius: 12px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            width: 320px;
            display: none;
            z-index: 100;
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

        .btn-cancel {{
            background: white;
            color: #6a6a6a;
            border: 2px solid #e5e5e5;
        }}

        .btn-cancel:hover:not(:disabled) {{
            background: #f5f5f7;
        }}

        .btn-confirm {{
            background: #8b5cf6;
            color: white;
        }}

        .btn-confirm:hover:not(:disabled) {{
            background: #6366f1;
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

        .completed-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: #f5f5f7;
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        .completed-overlay.hidden {{
            display: none;
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

        .takeover-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(4px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 60;
            cursor: pointer;
        }}

        .takeover-overlay.hidden {{
            display: none;
        }}

        .takeover-overlay-message {{
            text-align: center;
            color: white;
            padding: 40px;
            max-width: 500px;
        }}

        .takeover-overlay-message h3 {{
            font-size: 24px;
            margin: 0 0 16px 0;
            font-weight: 600;
        }}

        .takeover-overlay-message p {{
            font-size: 16px;
            margin: 0;
            line-height: 1.6;
            color: rgba(255, 255, 255, 0.9);
        }}

        .loading {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            color: white;
            background: #000;
            z-index: 50;
        }}

        .loading h3 {{
            margin: 0 0 8px 0;
        }}

        .loading p {{
            margin: 0;
        }}

        @media (max-width: 768px) {{
            .top-banner-content {{
                flex-direction: column;
                gap: 12px;
            }}

            .banner-left {{
                width: 100%;
            }}

            .control-section {{
                flex-direction: column;
            }}
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

    <!-- Top Banner -->
    <div class="top-banner">
        <div class="top-banner-content">
            <div class="banner-left">
                <div class="nova-icon">✨</div>
                <div class="banner-text">
                    <span class="banner-text-label">Nova Act needs your help:</span>
                    <span class="banner-text-message">{message_from_nova_act}</span>
                    <span class="banner-text-instruction">
                        You have connected to the browser session. Please take over the browser to complete the task.
                        The session expires in {time_to_expiry}.
                    </span>
                </div>
            </div>
            <!-- Control Section -->
            <div class="control-section">
                <span class="control-text">You are not in control.</span>
                <button id="takeover-btn" class="btn btn-takeover" onclick="takeControl()">
                    Take over
                </button>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <div class="main-container">
        <!-- Status message -->
        <div id="status" class="status-message"></div>

        <!-- Display wrapper container -->
        <div class="display-wrapper-container">
            <!-- Browser Streaming Section -->
            <div id="dcv-display-wrapper">
                <div id="dcv-display">
                    <!-- DCV canvas will be inserted here -->
                </div>

                <div class="loading">
                    <h3>Waiting for Session</h3>
                    <p>Session will be started externally</p>
                </div>

                <!-- Takeover Overlay -->
                <div id="takeover-overlay" class="takeover-overlay">
                    <div class="takeover-overlay-message">
                        <h3>Click "Take over" to begin</h3>
                        <p>
                            Click the "Take over" button in the top banner to access and control
                            the Nova Act agent browser.
                        </p>
                    </div>
                </div>

            </div>

            <!-- Circular Menu Button (Below dcv-display-wrapper) -->
            <div class="menu-container">
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
    </div>

        <!-- Task completion overlay -->
        <div id="completion-overlay" class="completed-overlay hidden">
            <div class="completed-content">
                <div class="nova-icon">✨</div>
                <h2 id="completion-title">Loading...</h2>
                <p id="completion-message">Please wait while we check the status of this request.</p>
            </div>
        </div>
    </div>

    <!-- Already completed view -->
    <div id="already-completed" class="already-completed hidden">
        <div class="already-completed-card">
            <div class="nova-icon">✨</div>
            <h1 id="already-completed-title"></h1>
            <p id="already-completed-message"></p>
        </div>
    </div>

    <!-- Stop Workflow Confirmation Dialog -->
    <div id="stop-confirmation-dialog" class="confirmation-dialog">
        <div class="confirmation-content">
            <h2>Are you sure you want to stop the workflow?</h2>
            <p>
                After you agree, Nova Act will immediately stop the workflow.
                You will need to contact your administrator to restart the agent.
            </p>
            <div class="confirmation-buttons">
                <button class="btn btn-cancel" onclick="closeStopConfirmation()">Cancel</button>
                <button class="btn btn-confirm" onclick="proceedWithStop()">Agree</button>
            </div>
        </div>
    </div>

    <!-- View Details Modal -->
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
                <button class="btn btn-cancel" onclick="closeDetailsModal()">Close</button>
            </div>
        </div>
    </div>

    <!-- Load DCV SDK from CloudFront -->
    <script src="{dcv_base_url}/dcv.js"></script>

    <script>
        // Fallback values if viewport not provided
        const FALLBACK_WIDTH = {dcv_display_width};
        const FALLBACK_HEIGHT = {dcv_display_height};

        // UI Takeover Viewer Class
        class UITakeoverViewer {{
            constructor(presignedUrl, containerId = 'dcv-display') {{
                this.presignedUrl = presignedUrl;
                this.containerId = containerId;
                this.connection = null;
                this.desiredWidth = 0;
                this.desiredHeight = 0;
                this.currentWidth = 0;
                this.currentHeight = 0;
                console.log('[UITakeoverViewer] Initialized with URL:', presignedUrl);
            }}

            getScaleToFit(sourceWidth, sourceHeight, destWidth, destHeight) {{
                // Calculate the scale factor based on width
                const scaleX = destWidth / sourceWidth;
                // Calculate the scale factor based on height
                const scaleY = destHeight / sourceHeight;

                // Return the minimum of the two scale factors to ensure the source fits entirely
                return Math.min(scaleX, scaleY);
            }}

            httpExtraSearchParamsCallBack(method, url, body, returnType) {{
                console.log(
                    '[UITakeoverViewer] httpExtraSearchParamsCallBack called:', {{ method, url, returnType }});
                const parsedUrl = new URL(this.presignedUrl);
                const params = parsedUrl.searchParams;
                console.log('[UITakeoverViewer] Returning auth params:', params.toString());
                return params;
            }}

            displayLayoutCallback(serverWidth, serverHeight, heads) {{
                console.log(`[UITakeoverViewer] Display layout callback: ${{serverWidth}}x${{serverHeight}}`);

                if (this.connection) {{
                    // Only request display if sizes have actually changed
                    if (this.desiredWidth > 0 && this.desiredHeight > 0 &&
                        (this.currentWidth !== this.desiredWidth || this.currentHeight !== this.desiredHeight)) {{
                        console.log(
                            `[UITakeoverViewer] Requesting display layout from ` +
                            `${{this.currentWidth}}x${{this.currentHeight}} to ` +
                            `${{this.desiredWidth}}x${{this.desiredHeight}}`
                        );

                        this.connection.requestDisplayLayout([{{
                            name: "Main Display",
                            rect: {{
                                x: 0,
                                y: 0,
                                width: this.desiredWidth,
                                height: this.desiredHeight
                            }},
                            primary: true
                        }}]).then(() => {{
                            this.connection.requestResolution(this.desiredWidth, this.desiredHeight).then(() => {{
                                console.log(
                                    `[UITakeoverViewer] Resolution successfully set to ` +
                                    `${{this.desiredWidth}}x${{this.desiredHeight}}`
                                );
                                const scale = this.getScaleToFit(
                                    this.desiredWidth,
                                    this.desiredHeight,
                                    this.desiredWidth,
                                    this.desiredHeight
                                );

                                this.connection.setDisplayScale(scale).then(() => {{
                                    console.log(`[UITakeoverViewer] Scale successfully set to ${{scale}}`);
                                    const canvas = document.getElementById(this.containerId);
                                    if (canvas) {{
                                        canvas.style.transform = `scale(1.0)`;
                                    }}

                                    this.currentWidth = this.desiredWidth;
                                    this.currentHeight = this.desiredHeight;
                                }});
                            }}).catch((err) => {{
                                console.error('[UITakeoverViewer] Failed to set resolution:', err);
                            }});
                        }});
                    }}
                }}
            }}

            async connect() {{
                return new Promise((resolve, reject) => {{
                    if (typeof window.dcv === 'undefined') {{
                        reject(new Error('DCV SDK not loaded'));
                        return;
                    }}

                    console.log('[UITakeoverViewer] DCV SDK loaded, version:', window.dcv.version || 'Unknown');
                    console.log('[UITakeoverViewer] Available DCV methods:', Object.keys(window.dcv));
                    console.log('[UITakeoverViewer] Presigned URL:', this.presignedUrl);

                    if (window.dcv.setLogLevel) {{
                        window.dcv.setLogLevel(window.dcv.LogLevel.DEBUG);
                        console.log('[UITakeoverViewer] DCV log level set to DEBUG');
                    }}

                    console.log('[UITakeoverViewer] Starting authentication...');

                    window.dcv.authenticate(this.presignedUrl, {{
                        promptCredentials: () => {{
                            console.warn(
                            '[UITakeoverViewer] DCV requested credentials - should not happen with presigned URL');
                        }},
                        error: (auth, error) => {{
                            console.error('[UITakeoverViewer] DCV auth error:', error);
                            console.error('[UITakeoverViewer] Error details:', {{
                                message: error.message || error,
                                code: error.code,
                                statusCode: error.statusCode,
                                stack: error.stack
                            }});
                            reject(error);
                        }},
                        success: (auth, result) => {{
                            console.log('[UITakeoverViewer] DCV auth success:', result);
                            if (result && result[0]) {{
                                const {{ sessionId, authToken }} = result[0];
                                console.log('[UITakeoverViewer] Session ID:', sessionId);
                                console.log('[UITakeoverViewer] Auth token received:', authToken ? 'Yes' : 'No');
                                this.connectToSession(sessionId, authToken, resolve, reject);
                            }} else {{
                                console.error('[UITakeoverViewer] No session data in auth result');
                                reject(new Error('No session data in auth result'));
                            }}
                        }},
                        httpExtraSearchParams: this.httpExtraSearchParamsCallBack.bind(this)
                    }});
                }});
            }}

            connectToSession(sessionId, authToken, resolve, reject) {{
                console.log('[UITakeoverViewer] Connecting to session:', sessionId);

                const connectOptions = {{
                    url: this.presignedUrl,
                    sessionId: sessionId,
                    authToken: authToken,
                    divId: this.containerId,
                    baseUrl: "{dcv_base_url}",
                    callbacks: {{
                        firstFrame: () => {{
                            console.log('[UITakeoverViewer] First frame received!');
                            resolve(this.connection);
                        }},
                        error: (error) => {{
                            console.error('[UITakeoverViewer] Connection error:', error);
                            reject(error);
                        }},
                        disconnect: () => {{
                            console.log('[UITakeoverViewer] DCV disconnected');
                        }},
                        httpExtraSearchParams: this.httpExtraSearchParamsCallBack.bind(this),
                        displayLayout: this.displayLayoutCallback.bind(this)
                    }}
                }};

                console.log('[UITakeoverViewer] Connect options:', connectOptions);

                window.dcv.connect(connectOptions)
                    .then(connection => {{
                        console.log('[UITakeoverViewer] Connection established:', connection);
                        this.connection = connection;
                    }})
                    .catch(error => {{
                        console.error('[UITakeoverViewer] Connect failed:', error);
                        reject(error);
                    }});
            }}

            setDisplaySize(width, height) {{
                this.desiredWidth = width;
                this.desiredHeight = height;

                if (this.connection) {{
                    this.displayLayoutCallback(null, 0, 0, []);
                }}
            }}

            disconnect() {{
                if (this.connection) {{
                    this.connection.disconnect();
                    this.connection = null;
                }}
            }}
        }}
    </script>

    <script>
        console.log('[UI Takeover] Script starting...');
        let viewer = null;
        let sessionData = null;
        let isTaskCompleted = false;
        let isInControl = false;

        const apiUrls = {json.dumps(params.api_urls, separators=(",", ":"), ensure_ascii=True)};
        const eventId = {json.dumps(event_id)};
        const apiToken = {json.dumps(event_id)};

        console.log('[UI Takeover] API URLs:', apiUrls);
        console.log('[UI Takeover] Event ID:', eventId);

        async function apiCall(url, data = {{}}) {{
            try {{
                const fetchOptions = {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${{apiToken}}`
                    }},
                    body: JSON.stringify(data)
                }};

                const response = await fetch(url, fetchOptions);

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

        async function fetchSessionInfo() {{
            try {{
                console.log('[UI Takeover] Fetching session info...');
                const sessionInfo = await apiCall(apiUrls.browser_session_info_url, {{
                    token: eventId,
                    remote_browser: apiUrls.remote_browser
                }});
                console.log('[UI Takeover] Session info received:', sessionInfo);

                if (sessionInfo.streams
                    && sessionInfo.streams.liveViewStream
                    && sessionInfo.streams.liveViewStream.presignedUrl) {{
                    const presignedUrl = sessionInfo.streams.liveViewStream.presignedUrl;
                    const sessionId = sessionInfo.sessionId;
                    const viewPort = sessionInfo.viewPort || {{
                        width: FALLBACK_WIDTH,
                        height: FALLBACK_HEIGHT
                    }};

                    await initializeSession(sessionId, presignedUrl, viewPort);
                }} else {{
                    throw new Error('No presigned URL in session info');
                }}

            }} catch (error) {{
                console.error('Failed to fetch session info:', error);
            }}
        }}

        async function initializeSession(sessionId, presignedUrl, viewPort) {{
            try {{
                console.log('[UI Takeover] Initializing session...');
                console.log('[UI Takeover] ViewPort:', viewPort);

                sessionData = {{
                    session_id: sessionId,
                    presigned_url: presignedUrl
                }};

                // Use viewport values with fallbacks
                const dcv_display_width = viewPort?.width ?? FALLBACK_WIDTH;
                const dcv_display_height = viewPort?.height ?? FALLBACK_HEIGHT;

                // Calculate aspect ratio
                const aspectRatio = dcv_display_width / dcv_display_height;

                // Update dcv-display-wrapper dimensions based on viewport
                const viewportWidthPadding = 20;
                const viewportHeightPadding = 90;
                const wrapper = document.getElementById('dcv-display-wrapper');
                if (wrapper) {{
                    wrapper.style.aspectRatio = aspectRatio.toString();
                    console.log(
                        '[UI Takeover] Updated display dimensions to',
                        dcv_display_width + viewportWidthPadding,
                        'x',
                        dcv_display_height + viewportHeightPadding,
                        'with aspect ratio',
                        aspectRatio
                    );
                }}

                await connectToStream(presignedUrl, viewPort);

            }} catch (error) {{
                console.error('[UI Takeover] Failed to initialize session:', error);
            }}
        }}

        async function connectToStream(presignedUrl, viewPort) {{
            try {{
                if (typeof window.dcv === 'undefined') {{
                    throw new Error('DCV SDK not loaded');
                }}

                // Clear loading message
                const loadingEl = document.querySelector('#dcv-display-wrapper .loading');
                if (loadingEl) loadingEl.remove();

                viewer = new UITakeoverViewer(presignedUrl, 'dcv-display');

                // Use viewport dimensions from session info with fallbacks
                const container = document.getElementById('dcv-display');
                const containerWidth = container.clientWidth || container.offsetWidth;
                const containerHeight = container.clientHeight || container.offsetHeight;

                console.log('[UI Takeover] Setting display size to', containerWidth, 'x', containerHeight);
                viewer.setDisplaySize(containerWidth, containerHeight);

                await viewer.connect();

                console.log('[UI Takeover] Connected to browser session');

            }} catch (error) {{
                console.error('Failed to connect to stream:', error);
            }}
        }}

        function showStatus(message, isError = false) {{
            const statusEl = document.getElementById('status');
            statusEl.textContent = message;
            statusEl.className = 'status-message ' + (isError ? 'error' : 'success');
            statusEl.style.display = 'block';
        }}

        function hideStatus() {{
            document.getElementById('status').style.display = 'none';
        }}

        function takeControl() {{
            isInControl = true;

            // Hide the takeover overlay
            const takeoverOverlay = document.getElementById('takeover-overlay');
            if (takeoverOverlay) {{
                takeoverOverlay.classList.add('hidden');
            }}

            const controlText = document.querySelector('.control-text');
            controlText.textContent = 'You are in control.';
            controlText.style.color = '#16a34a';

            const takeoverBtn = document.getElementById('takeover-btn');
            takeoverBtn.textContent = 'Complete task';
            takeoverBtn.onclick = completeTask;

            hideStatus();
            console.log('[UI Takeover] User took control');
        }}

        async function completeTask() {{
            if (isTaskCompleted) return;

            const takeoverBtn = document.getElementById('takeover-btn');
            takeoverBtn.disabled = true;

            try {{
                console.log('[UI Takeover] Completing task...');
                showStatus('Completing task...');

                const result = await apiCall(apiUrls.complete_task_url, {{
                    token: eventId,
                    remote_browser: apiUrls.remote_browser
                }});

                if (result.task_completed) {{
                    showCompletionOverlay('completed');
                    console.log('[UI Takeover] Task completed successfully');
                }} else {{
                    showStatus('Failed to complete task: ' + (result.error || result.message), true);
                    takeoverBtn.disabled = false;
                    console.error('Failed to complete task:', result);
                }}
            }} catch (error) {{
                showStatus('Error completing task: ' + error.message, true);
                takeoverBtn.disabled = false;
                console.error('Error completing task:', error);
            }}
        }}

        function confirmStopWorkflow() {{
            document.getElementById('stop-confirmation-dialog').classList.add('show');
        }}

        function closeStopConfirmation() {{
            document.getElementById('stop-confirmation-dialog').classList.remove('show');
        }}

        async function proceedWithStop() {{
            closeStopConfirmation();

            const takeoverBtn = document.getElementById('takeover-btn');
            if (takeoverBtn) takeoverBtn.disabled = true;

            try {{
                console.log('[UI Takeover] Stopping workflow...');
                showStatus('Stopping workflow...');

                const result = await apiCall(apiUrls.terminate_workflow_url, {{
                    token: eventId,
                    remote_browser: apiUrls.remote_browser
                }});

                if (result.workflow_terminated) {{
                    showCompletionOverlay('terminated');
                    console.log('[UI Takeover] Workflow terminated successfully');
                }} else {{
                    showStatus('Failed to stop workflow: ' + (result.error || result.message), true);
                    if (takeoverBtn) takeoverBtn.disabled = false;
                    console.error('Failed to stop workflow:', result);
                }}
            }} catch (error) {{
                showStatus('Error stopping workflow: ' + error.message, true);
                if (takeoverBtn) takeoverBtn.disabled = false;
                console.error('Error stopping workflow:', error);
            }}
        }}

        function showCompletionOverlay(action, errorDetails = null) {{
            isTaskCompleted = true;
            if (viewer) viewer.disconnect();
            hideStatus();

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
            }} else if (action === 'completed') {{
                title.textContent = 'Request is completed!';
                message.innerHTML =
                    'This takeover request has already been completed. Contact your admin to ' +
                    'get more information about the request or workflow status.<br><br>' +
                    'There\\'s no further action needed.';
            }} else if (action === 'terminated') {{
                title.textContent = 'Request is completed!';
                message.innerHTML =
                    'This workflow has already been stopped. Contact your admin to ' +
                    'get more information about the request or workflow status.<br><br>' +
                    'There\\'s no further action needed.';
            }}

            // Ensure overlay is visible (remove hidden class if present)
            overlay.classList.remove('hidden');
        }}

        function closeDetailsModal(event) {{
            if (!event || event.target.id === 'details-modal' ||
                event.target.classList.contains('btn-cancel')) {{
                document.getElementById('details-modal').classList.remove('show');
            }}
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

            // Show details modal with workflow information
            const modal = document.getElementById('details-modal');
            const detailsBody = document.getElementById('details-body');

            // Populate details
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

        // Close menu when clicking outside
        document.addEventListener('click', function(event) {{
            const menu = document.getElementById('menu-dropdown');
            const menuButton = document.getElementById('menu-button');
            if (menu && menuButton && !menuButton.contains(event.target)) {{
                menu.classList.remove('show');
            }}
        }});

        async function checkTaskStatus() {{
            if (!eventId) return false;

            try {{
                const data = await apiCall(apiUrls.task_status_url, {{
                    token: eventId,
                    remote_browser: apiUrls.remote_browser
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
                console.error('[UI Takeover] Error checking task status:', error);
            }}
            return false;
        }}

        function showAlreadyCompletedView() {{
            // Update the message
            document.getElementById('already-completed-title').textContent =
                'The Request has been Completed!';
            document.getElementById('already-completed-message').textContent =
                'This takeover request has already been completed. Contact your admin to ' +
                'get more information about the request or workflow status.';

            // Show the already-completed view
            const alreadyCompleted = document.getElementById('already-completed');
            alreadyCompleted.classList.remove('hidden');
        }}

        // Clean up on page unload
        window.addEventListener('beforeunload', () => {{
            if (viewer) viewer.disconnect();
        }});

        // Initialize the page
        document.addEventListener('DOMContentLoaded', async () => {{
            console.log('[UI Takeover] Page loaded');

            // Check task completion status first
            if (await checkTaskStatus()) {{
                // Task is completed, hide initial loading and show completion overlay
                const initialLoading = document.getElementById('initial-loading-overlay');
                initialLoading.classList.add('hidden');
                return;
            }}

            // Task is not completed, hide both overlays
            const initialLoading = document.getElementById('initial-loading-overlay');
            initialLoading.classList.add('hidden');

            const overlay = document.getElementById('completion-overlay');
            overlay.classList.add('hidden');

            // Check if DCV SDK is loaded
            if (typeof window.dcv !== 'undefined') {{
                console.log('[UI Takeover] DCV SDK loaded successfully');
                if (window.dcv.setWorkerPath) {{
                    window.dcv.setWorkerPath('{dcv_base_url}/');
                    console.log('[UI Takeover] Set DCV worker path');
                }}
            }} else {{
                console.error('[UI Takeover] DCV SDK not found!');
                return;
            }}

            // Fetch session info if task is not completed
            if (eventId && !isTaskCompleted) {{
                console.log('[UI Takeover] Fetching session info from API');
                fetchSessionInfo();
            }} else if (!eventId) {{
                console.error('[UI Takeover] No eventId provided');
            }}

            // Signal that SPA is ready
            if (window.parent !== window) {{
                window.parent.postMessage({{ type: 'SPA_READY' }}, '*');
            }}
        }});
    </script>
</body>
</html>"""

        return spa_html


def spa_generator_handler(event: GenericDict, context: LambdaContext) -> JSONType:
    """Lambda handler for SPA generation."""
    return UITakeoverWorkflowHandler().handle_spa_generator(event, context)


def confirm_if_answered(event: GenericDict, context: LambdaContext) -> JSONType:
    """Lambda handler for confirmation check."""
    return UITakeoverWorkflowHandler().handle_confirm_if_answered(event, context)


@event_source(data_class=EventBridgeEvent)
def completion_handler(event: EventBridgeEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for workflow completion."""
    return UITakeoverWorkflowHandler().handle_completion(event, context)
