"""Tests for step function models."""

import pytest

from amzn_nova_act_human_intervention_common.models.common_models import UseCase
from amzn_nova_act_human_intervention_common.models.step_function_models import (
    ApprovalStepFunctionInput,
    StepFunctionInput,
    UITakeoverStepFunctionInput,
)


class TestStepFunctionInputFromPayload:
    """Test StepFunctionInput.from_payload class method."""

    def test_from_payload_ui_takeover(self):
        """Test conversion to UITakeoverStepFunctionInput."""
        payload = {
            "workflow_run_id": "run123",
            "session_id": "session123",
            "act_id": "act123",
            "event_id": "event123",
            "type": UseCase.UI_TAKEOVER,
            "timeout": 300,
            "notification_recipients": [
                {
                    "contact_info": {
                        "type": "email",
                        "to_email_address": "test@example.com",
                        "from_email_address": "noreply@example.com",
                    }
                }
            ],
            "message": "Test message",
            "remote_browser": {"session_id": "browser123"},
        }

        result = StepFunctionInput.from_payload(payload)

        assert isinstance(result, UITakeoverStepFunctionInput)
        assert result.type == UseCase.UI_TAKEOVER
        assert result.message == "Test message"

    def test_from_payload_approval(self):
        """Test conversion to ApprovalStepFunctionInput."""
        payload = {
            "workflow_run_id": "run123",
            "session_id": "session123",
            "act_id": "act123",
            "event_id": "event123",
            "type": UseCase.APPROVAL,
            "timeout": 300,
            "notification_recipients": [
                {
                    "contact_info": {
                        "type": "email",
                        "to_email_address": "test@example.com",
                        "from_email_address": "noreply@example.com",
                    }
                }
            ],
            "query": "Approve this action?",
            "options": [
                {"label": "Yes", "action": "APPROVE"},
                {"label": "No", "action": "DENY"},
            ],
            "most_recent_screenshot": "base64_screenshot_data",
        }

        result = StepFunctionInput.from_payload(payload)

        assert isinstance(result, ApprovalStepFunctionInput)
        assert result.type == UseCase.APPROVAL
        assert result.query == "Approve this action?"
        assert len(result.options) == 2
        assert result.options[0].label == "Yes"
        assert result.options[0].action.value == "APPROVE"
        assert result.options[1].label == "No"
        assert result.options[1].action.value == "DENY"

    def test_from_payload_unsupported_use_case(self):
        """Test error for unsupported use case."""
        payload = {
            "workflow_run_id": "run123",
            "session_id": "session123",
            "act_id": "act123",
            "event_id": "event123",
            "type": "INVALID_TYPE",
            "timeout": 300,
            "notification_recipients": [
                {
                    "contact_info": {
                        "type": "email",
                        "to_email_address": "test@example.com",
                        "from_email_address": "noreply@example.com",
                    }
                }
            ],
        }

        with pytest.raises(ValueError):
            StepFunctionInput.from_payload(payload)
