"""Workflow execution error exception."""

from amzn_nova_act_human_intervention_common import ExecutionStatus


class WorkflowExecutionError(Exception):
    """Exception raised when a workflow execution is terminated by the user.

    This exception is raised when a workflow completes with a TERMINATED status,
    indicating that the user explicitly cancelled or terminated the intervention.
    This is distinct from workflow failures (FAILED status) which raise RuntimeError.

    Use this exception to distinguish between:
    - User-initiated cancellations (TERMINATED) → Handle gracefully, return CANCEL
    - System/workflow failures (FAILED) → Re-raise for proper error handling

    Attributes
    ----------
    status : ExecutionStatus
        The execution status (TERMINATED)
    message : str
        Detailed error message describing the termination
    workflow_type : str
        Type of workflow that was terminated (e.g., "Approval", "UI Takeover")

    Examples
    --------
    Handling workflow termination in an approval flow:

    >>> from amzn_nova_act_human_intervention_client import (
    ...     ApprovalInterventionExecutor,
    ...     WorkflowExecutionError
    ... )
    >>> from amzn_nova_act_human_intervention_common import ExecutionStatus
    >>>
    >>> try:
    ...     executor.run(approval_request)
    ...     # Process successful approval
    ...     decision = executor.completion_response.get("approvalAction")
    ...     print(f"User decision: {decision}")
    ... except WorkflowExecutionError as e:
    ...     # User cancelled/terminated - handle gracefully
    ...     if e.status == ExecutionStatus.TERMINATED:
    ...         print(f"User cancelled the approval: {e.message}")
    ...         # Return CANCEL or handle appropriately
    ...     else:
    ...         # Unexpected status
    ...         raise
    ... except RuntimeError as e:
    ...     # System failure - re-raise or handle error
    ...     print(f"Workflow failed: {e}")
    ...     raise

    Checking specific workflow type:

    >>> try:
    ...     executor.run(takeover_request)
    ... except WorkflowExecutionError as e:
    ...     print(f"Workflow type: {e.workflow_type}")
    ...     print(f"Status: {e.status.value}")
    ...     print(f"Message: {e.message}")
    Workflow type: UI Takeover
    Status: TERMINATED
    Message: UI Takeover workflow failed with status TERMINATED: User cancelled the intervention

    Re-raising with additional context:

    >>> try:
    ...     executor.run(approval_request)
    ... except WorkflowExecutionError as e:
    ...     # Log and re-raise with additional context
    ...     logger.error(f"Approval workflow terminated: {e.workflow_type}")
    ...     raise RuntimeError(f"Cannot proceed without approval: {e.message}") from e
    """

    def __init__(self, status: ExecutionStatus, workflow_type: str, message: str | None = None) -> None:
        """Initialize WorkflowExecutionError.

        Parameters
        ----------
        status : ExecutionStatus
            The execution status (typically TERMINATED for user-initiated cancellation)
        workflow_type : str
            Type of workflow that was terminated (e.g., "Approval", "UI Takeover")
        message : str, optional
            Additional context about the termination, by default None
        """
        self.status = status
        self.workflow_type = workflow_type

        if message:
            error_message = f"{workflow_type} workflow failed with status {status.value}: {message}"
        else:
            error_message = f"{workflow_type} workflow failed with status: {status.value}"

        super().__init__(error_message)
        self.message = error_message
