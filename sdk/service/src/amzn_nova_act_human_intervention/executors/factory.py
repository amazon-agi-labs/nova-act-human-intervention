"""Factory for creating human intervention executors."""

from typing import Dict, Type

from amzn_nova_act_human_intervention.executors.base import BaseInterventionExecutor, ExecutorType
from amzn_nova_act_human_intervention.executors.websocket import WebSocketService


class ExecutorFactory:
    """Factory class for creating intervention executors.

    Provides a centralized way to create different types of intervention executors
    based on the specified executor type and configuration.
    """

    _executor_registry: Dict[ExecutorType, Type[BaseInterventionExecutor]] = {
        ExecutorType.WEBSOCKET: WebSocketService,
    }

    @classmethod
    def create_executor(cls, executor_type: ExecutorType, endpoint: str) -> BaseInterventionExecutor:
        """Create an intervention executor of the specified type.

        Args:
            executor_type: Type of executor to create
            endpoint: Connection endpoint for the executor

        Returns:
            Configured intervention executor instance

        Raises:
            ValueError: If executor type is not supported

        Example:
            >>> from amzn_nova_act_human_intervention.executors import ExecutorFactory, ExecutorType
            >>> executor = ExecutorFactory.create_executor(
            ...     executor_type=ExecutorType.WEBSOCKET,
            ...     endpoint="wss://api.example.com/prod"
            ... )
            >>> # Returns a WebSocketService instance
        """
        if executor_type not in cls._executor_registry:
            raise ValueError(f"Unsupported executor type: {executor_type}")

        executor_class = cls._executor_registry[executor_type]
        return executor_class(endpoint)

    @classmethod
    def register_executor(cls, executor_type: ExecutorType, executor_class: Type[BaseInterventionExecutor]) -> None:
        """Register a new executor type.

        Allows external packages to register their own executor implementations.

        Args:
            executor_type: Type identifier for the executor
            executor_class: Executor class that implements BaseInterventionExecutor

        Raises:
            TypeError: If executor_class doesn't inherit from BaseInterventionExecutor

        Example:
            >>> from amzn_nova_act_human_intervention.executors import ExecutorFactory, ExecutorType
            >>> from enum import Enum
            >>> class MyExecutorType(Enum):
            ...     CUSTOM = "custom"
            >>> class MyCustomExecutor(BaseInterventionExecutor):
            ...     pass
            >>> ExecutorFactory.register_executor(MyExecutorType.CUSTOM, MyCustomExecutor)
        """
        if not issubclass(executor_class, BaseInterventionExecutor):
            raise TypeError("Executor class must inherit from BaseInterventionExecutor")

        cls._executor_registry[executor_type] = executor_class

    @classmethod
    def get_supported_types(cls) -> list[ExecutorType]:
        """Get list of supported executor types.

        Returns:
            List of supported executor types
        """
        return list(cls._executor_registry.keys())
