"""Core intervention models for Nova Act Human Intervention."""

from pydantic import BaseModel


class InterventionContext(BaseModel):
    """Context information for intervention execution.

    Attributes
    ----------
    workflow_run_id : str
        Unique identifier for the intervention run
    act_session_id : str
        Session ID for the Act session
    act_id : str
        Unique identifier for the Act

    Examples
    --------
    Intervention context::

        {
            "workflow_run_id": "12345678-1234-1234-1234-123456789012",
            "act_session_id": "87654321-4321-4321-4321-210987654321",
            "act_id": "abcdef12-3456-7890-abcd-ef1234567890"
        }
    """

    workflow_run_id: str
    act_session_id: str
    act_id: str


class BrowserSessionContext(BaseModel):
    """Browser session context for remote browser control.

    Attributes
    ----------
    session_id : str
        Browser session identifier (ULID format)

    Examples
    --------
    Browser session context::

        {
            "session_id": "01K7QQZ3BDK9HBE6KT05MSQHK6"
        }
    """

    session_id: str
