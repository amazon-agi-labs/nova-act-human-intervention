"""Base classes for intervention executors."""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Generic, TypeVar

from amzn_nova_act_human_intervention_common import InterventionContext, LoggingConfig

# Input data type for intervention requests (e.g., ApprovalRequest, UITakeoverRequest).
# Both are Pydantic models.
T = TypeVar("T")


class ExecutorType(Enum):
    """Available intervention executor implementation types."""

    WEBSOCKET = "websocket"


class BaseInterventionExecutor(Generic[T], ABC):
    """Abstract base class for intervention executors.

    Defines the interface for executing human intervention processes.
    Subclasses must implement the run() method to handle specific intervention types.

    Type Parameters
    ---------------
    T : TypeVar
        The type of input data for the intervention (e.g., ApprovalRequest, UITakeoverRequest)

    Examples
    --------
    Implementing a custom intervention executor:

    >>> from amzn_nova_act_human_intervention_client import BaseInterventionExecutor
    >>> from amzn_nova_act_human_intervention_common import InterventionContext
    >>>
    >>> class MyCustomExecutor(BaseInterventionExecutor[dict]):
    ...     def __init__(self, endpoint: str, context: InterventionContext):
    ...         super().__init__(endpoint, context)
    ...
    ...     def run(self, input_data: dict) -> None:
    ...         self.logger.info(f"Processing intervention: {input_data}")
    ...         # Implement custom intervention logic
    ...         self.completion_response = {"status": "completed"}
    """

    def __init__(self, endpoint: str, intervention_context: InterventionContext) -> None:
        """Initialize the intervention executor.

        Args:
            endpoint: Connection endpoint
            intervention_context: Context information for the intervention
        """
        self._endpoint: str = endpoint
        self._intervention_context: InterventionContext = intervention_context
        self.completion_response: Dict[str, Any] | None = None
        self.logger: logging.Logger = LoggingConfig.get_logger(type(self).__name__)

    @abstractmethod
    def run(self, input_data: T) -> None:
        """Execute intervention with input data.

        Args:
            input_data: Intervention-specific input data
        """
