"""Models for workflow SPA generation.

This module provides base and specific models for generating SPAs across different workflows.
"""

from typing import Dict, List

from amzn_nova_act_human_intervention_common import ApprovalOption, GenericDict
from pydantic import BaseModel, Field


class BaseSPAGeneratorParams(BaseModel):
    """Base parameters common to all SPA generators.

    Attributes
    ----------
    session_name : str
        Name/identifier for the session
    spa_type : str
        Type of SPA (e.g., "ui_takeover", "approval")
    api_urls : GenericDict
        Dictionary of API endpoint URLs for the SPA
    """

    session_name: str = Field(..., description="Session name/identifier")
    spa_type: str = Field(..., description="Type of SPA")
    api_urls: GenericDict = Field(..., description="API endpoint URLs")


class UITakeoverSPAParams(BaseSPAGeneratorParams):
    """Parameters for generating UI Takeover SPA.

    Inherits common SPA parameters and adds UI takeover specific fields.

    Attributes
    ----------
    message : str
        The message to display to the user from Nova Act
    remote_browser : Dict[str, str]
        Remote browser configuration containing session_id
    timeout : int
        Timeout in seconds for the session
    workflow_run_id : str
        Unique identifier for the workflow run
    act_id : str
        Unique identifier for the Act
    session_id : str
        Session ID for the UI takeover session

    Examples
    --------
    SPA generator params::

        {
            "message": "Please complete the reCAPTCHA.",
            "session_name": "ui-takeover-12345",
            "spa_type": "ui_takeover",
            "remote_browser": {"session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"},
            "api_urls": {
                "browser_session_info_url": "https://...",
                "complete_task_url": "https://...",
                "terminate_workflow_url": "https://...",
                "task_status_url": "https://...",
                "view_details_url": "https://...",
                "remote_browser": {"session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"}
            },
            "timeout": 25200,
            "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            "session_id": "87654321-4321-4321-4321-210987654321"
        }
    """

    message: str = Field(..., description="Message to display to the user")
    remote_browser: Dict[str, str] = Field(..., description="Remote browser configuration")
    timeout: int = Field(..., gt=0, description="Session timeout in seconds")
    workflow_run_id: str = Field(..., description="Workflow run identifier")
    act_id: str = Field(..., description="Act identifier")
    session_id: str = Field(..., description="Session identifier")


class ApprovalSPAParams(BaseSPAGeneratorParams):
    """Parameters for generating Approval SPA.

    Inherits common SPA parameters and adds approval specific fields.

    Attributes
    ----------
    message : str
        The approval request message to display to the user
    timeout : int
        Timeout in seconds for the approval decision
    workflow_run_id : str
        Unique identifier for the workflow run
    act_id : str
        Unique identifier for the Act
    session_id : str
        Session ID for the approval session
    screenshot : str | None
        Optional base64 encoded screenshot to display

    Examples
    --------
    SPA generator params::

        {
            "message": "Please approve this purchase request.",
            "session_name": "approval-12345",
            "spa_type": "approval",
            "api_urls": {
                "record_response_url": "https://...",
                "task_status_url": "https://...",
                "view_details_url": "https://..."
            },
            "timeout": 3600,
            "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            "act_id": "abcdef12-3456-7890-abcd-ef1234567890",
            "session_id": "87654321-4321-4321-4321-210987654321",
            "screenshot": "iVBORw0KGgoAAAANS..."
        }
    """

    message: str = Field(..., description="Approval request message")
    options: List[ApprovalOption] = Field(..., description="List of approval options")
    timeout: int = Field(..., gt=0, description="Session timeout in seconds")
    workflow_run_id: str = Field(..., description="Workflow run identifier")
    act_id: str = Field(..., description="Act identifier")
    session_id: str = Field(..., description="Session identifier")
    screenshot: str | None = Field(None, description="Optional base64 screenshot")
