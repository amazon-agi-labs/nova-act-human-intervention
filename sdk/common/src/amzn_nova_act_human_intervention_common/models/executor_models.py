"""Executor models for Nova Act Human Intervention."""

from pydantic import BaseModel

from amzn_nova_act_human_intervention_common.models.type_definitions import InterventionRequest


class ExecutorRequest(BaseModel):
    """Executor message structure for Lambda handlers.

    Attributes
    ----------
    action : str, optional
        Action to perform (e.g., "start_intervention")
    input : InterventionRequest
        Step function input data (UITakeoverStepFunctionInput or ApprovalStepFunctionInput)

    Examples
    --------
    Executor request for UI Takeover::

        {
            "action": "start_intervention",
            "input": {
                "workflow_run_id": "12345678-1234-1234-1234-123456789012",
                "session_id": "87654321-4321-4321-4321-210987654321",
                "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
                "event_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "type": "UITakeover",
                "timeout": 86400,
                "notification_recipients": [
                    {
                        "contact_info": "user@example.com",
                        "channel": "Email"
                    }
                ],
                "message": "Please complete the form submission",
                "remote_browser": {
                    "session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"
                }
            }
        }
    """

    action: str | None
    input: InterventionRequest
