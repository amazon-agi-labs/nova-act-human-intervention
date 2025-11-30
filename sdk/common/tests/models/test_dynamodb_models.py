"""Unit tests for DynamoDB models."""

from unittest.mock import patch

import pytest

from amzn_nova_act_human_intervention_common.models.common_models import (
    EmailContactInfo,
    NotificationChannel,
    NotificationRecipient,
    UseCase,
)
from amzn_nova_act_human_intervention_common.models.dynamodb_models import (
    ConnectionItem,
    ErrorCode,
    ErrorDetails,
    ExecutionItem,
)
from amzn_nova_act_human_intervention_common.models.intervention_models import BrowserSessionContext
from amzn_nova_act_human_intervention_common.models.request_models import ApprovalAction, ApprovalOption
from amzn_nova_act_human_intervention_common.models.step_function_models import (
    ApprovalStepFunctionInput,
    UITakeoverStepFunctionInput,
)


class TestConnectionItem:
    def test_create(self):
        with patch("time.time", return_value=1703097600):
            item = ConnectionItem.create("test-connection-id", 3600)

        assert item.connectionId == "test-connection-id"
        assert item.timestamp == 1703097600
        assert item.ttl == 1703101200


class TestExecutionItem:
    @pytest.fixture
    def notification_recipients(self):
        return [
            NotificationRecipient(
                contact_info=EmailContactInfo(
                    to_email_address="user@example.com", from_email_address="noreply@example.com"
                )
            )
        ]

    @pytest.fixture
    def ui_takeover_input(self, notification_recipients):
        return UITakeoverStepFunctionInput(
            workflow_run_id="workflow-123",
            session_id="session-456",
            act_id="act-789",
            event_id="event-abc",
            type=UseCase.UI_TAKEOVER,
            timeout=86400,
            notification_recipients=notification_recipients,
            message="Complete the form",
            remote_browser=BrowserSessionContext(session_id="browser-123"),
        )

    @pytest.fixture
    def approval_input(self, notification_recipients):
        return ApprovalStepFunctionInput(
            workflow_run_id="workflow-123",
            session_id="session-456",
            act_id="act-789",
            event_id="event-abc",
            type=UseCase.APPROVAL,
            timeout=86400,
            notification_recipients=notification_recipients,
            query="Approve purchase?",
            options=[
                ApprovalOption(label="Approve", action=ApprovalAction.APPROVE),
                ApprovalOption(label="Cancel", action=ApprovalAction.DENY),
            ],
            most_recent_screenshot="base64-screenshot",
        )

    def test_create_ui_takeover(self, ui_takeover_input):
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=ui_takeover_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        assert item.eventId == "event-123"
        assert item.connectionId == "conn-456"
        assert item.workflowRunId == "workflow-123"
        assert item.interventionType == UseCase.UI_TAKEOVER
        assert item.message == "Complete the form"
        assert item.remoteBrowserSessionId == "browser-123"
        assert item.query is None
        assert item.options is None
        assert item.createdAt == 1703097600
        assert item.updatedAt == 1703097600
        assert item.ttl == 1703101200
        assert item.approvalAction is None

    def test_create_approval(self, approval_input):
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=approval_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        assert item.eventId == "event-123"
        assert item.interventionType == UseCase.APPROVAL
        assert item.query == "Approve purchase?"
        assert item.options == [
            {"label": "Approve", "action": "APPROVE"},
            {"label": "Cancel", "action": "DENY"},
        ]
        assert item.mostRecentScreenshot == "base64-screenshot"
        assert item.message is None
        assert item.remoteBrowserSessionId is None
        assert item.createdAt == 1703097600
        assert item.updatedAt == 1703097600
        assert item.ttl == 1703101200
        assert item.approvalAction is None

    def test_get_notification_recipients(self, ui_takeover_input):
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=ui_takeover_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        recipients = item.get_notification_recipients()
        assert len(recipients) == 1
        assert isinstance(recipients[0].contact_info, EmailContactInfo)
        assert recipients[0].contact_info.to_email_address == "user@example.com"
        assert recipients[0].channel == NotificationChannel.EMAIL

    def test_get_approval_options(self, approval_input):
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=approval_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        options = item.get_approval_options()
        assert options is not None
        assert len(options) == 2
        assert options[0].label == "Approve"
        assert options[0].action == ApprovalAction.APPROVE
        assert options[1].label == "Cancel"
        assert options[1].action == ApprovalAction.DENY

    def test_get_approval_options_none(self, ui_takeover_input):
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=ui_takeover_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        options = item.get_approval_options()
        assert options is None

    def test_get_error_details_none(self, ui_takeover_input):
        """Test get_error_details returns None when errorDetails not set."""
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=ui_takeover_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        error_details = item.get_error_details()
        assert error_details is None

    def test_set_and_get_error_details(self, ui_takeover_input):
        """Test setting and getting error details."""
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=ui_takeover_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        # Create and set error details directly
        error_details = ErrorDetails(
            code="TIMEOUT",
            message="This request has expired. The time limit for completing this task has been exceeded.",
        )
        item.errorDetails = error_details.model_dump()

        # Get error details back
        retrieved_details = item.get_error_details()
        assert retrieved_details is not None
        assert retrieved_details.code == "TIMEOUT"
        assert (
            retrieved_details.message
            == "This request has expired. The time limit for completing this task has been exceeded."
        )

    def test_error_details_serialization(self, ui_takeover_input):
        """Test that error details are properly serialized to dict."""
        with patch("time.time", return_value=1703097600):
            item = ExecutionItem.from_step_function_input(
                event_id="event-123",
                connection_id="conn-456",
                execution_arn="arn:aws:states:execution",
                step_function_input=ui_takeover_input,
                ttl_seconds=3600,
                execution_endpoint="wss://api.example.com/ws",
            )

        error_details = ErrorDetails.from_error_code(ErrorCode.BROWSER_SESSION_TERMINATED)
        item.errorDetails = error_details.model_dump()

        # Check that errorDetails is stored as dict
        assert isinstance(item.errorDetails, dict)
        assert item.errorDetails["code"] == "BROWSER_SESSION_TERMINATED"
        assert "message" in item.errorDetails


class TestErrorCode:
    """Test cases for ErrorCode enum."""

    def test_error_codes_exist(self):
        """Test that all expected error codes are defined."""
        assert ErrorCode.TIMEOUT == "TIMEOUT"
        assert ErrorCode.BROWSER_SESSION_TERMINATED == "BROWSER_SESSION_TERMINATED"
        assert ErrorCode.PAGE_GENERATION_FAILED == "PAGE_GENERATION_FAILED"
        assert ErrorCode.NOTIFICATION_FAILED == "NOTIFICATION_FAILED"
        assert ErrorCode.SYSTEM_ERROR == "SYSTEM_ERROR"
        assert ErrorCode.EXECUTION_FAILED == "EXECUTION_FAILED"

    def test_error_codes_are_strings(self):
        """Test that error codes are string type."""
        for error_code in ErrorCode:
            assert isinstance(error_code.value, str)


class TestErrorDetails:
    """Test cases for ErrorDetails model."""

    def test_create_error_details(self):
        """Test creating ErrorDetails directly."""
        error = ErrorDetails(code="TIMEOUT", message="Request timed out")

        assert error.code == "TIMEOUT"
        assert error.message == "Request timed out"

    def test_from_error_code_timeout(self):
        """Test creating ErrorDetails from TIMEOUT error code."""
        error = ErrorDetails.from_error_code(ErrorCode.TIMEOUT)

        assert error.code == "TIMEOUT"
        assert error.message == "This request has expired. The time limit for completing this task has been exceeded."

    def test_from_error_code_browser_terminated(self):
        """Test creating ErrorDetails from BROWSER_SESSION_TERMINATED error code."""
        error = ErrorDetails.from_error_code(ErrorCode.BROWSER_SESSION_TERMINATED)

        assert error.code == "BROWSER_SESSION_TERMINATED"
        assert error.message == "The browser session has been terminated. The remote browser is no longer available."

    def test_from_error_code_page_generation_failed(self):
        """Test creating ErrorDetails from PAGE_GENERATION_FAILED error code."""
        error = ErrorDetails.from_error_code(ErrorCode.PAGE_GENERATION_FAILED)

        assert error.code == "PAGE_GENERATION_FAILED"
        assert error.message == "Failed to generate the user interface. Please contact your administrator."

    def test_from_error_code_notification_failed(self):
        """Test creating ErrorDetails from NOTIFICATION_FAILED error code."""
        error = ErrorDetails.from_error_code(ErrorCode.NOTIFICATION_FAILED)

        assert error.code == "NOTIFICATION_FAILED"
        assert (
            error.message
            == "Failed to send notifications. The request may not have been delivered to the intended recipients."
        )

    def test_from_error_code_system_error(self):
        """Test creating ErrorDetails from SYSTEM_ERROR error code."""
        error = ErrorDetails.from_error_code(ErrorCode.SYSTEM_ERROR)

        assert error.code == "SYSTEM_ERROR"
        assert (
            error.message == "A system error occurred while processing this request. Please contact your administrator."
        )

    def test_from_error_code_execution_failed(self):
        """Test creating ErrorDetails from EXECUTION_FAILED error code."""
        error = ErrorDetails.from_error_code(ErrorCode.EXECUTION_FAILED)

        assert error.code == "EXECUTION_FAILED"
        assert error.message == "The workflow execution failed. Please contact your administrator for more information."

    def test_error_details_serialization(self):
        """Test that ErrorDetails can be serialized to dict."""
        error = ErrorDetails.from_error_code(ErrorCode.TIMEOUT)
        error_dict = error.model_dump()

        assert isinstance(error_dict, dict)
        assert error_dict["code"] == "TIMEOUT"
        assert "message" in error_dict

    def test_error_details_deserialization(self):
        """Test that ErrorDetails can be deserialized from dict."""
        error_dict = {
            "code": "SYSTEM_ERROR",
            "message": ("A system error occurred while processing this request. Please contact your administrator."),
        }
        error = ErrorDetails(**error_dict)

        assert error.code == "SYSTEM_ERROR"
        assert (
            error.message == "A system error occurred while processing this request. Please contact your administrator."
        )
