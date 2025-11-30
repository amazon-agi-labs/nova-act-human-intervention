from amzn_nova_act_human_intervention_common.models.common_models import (
    ContactInfo,
    EmailContactInfo,
    NotificationChannel,
    NotificationRecipient,
    SlackContactInfo,
    SlackTargetType,
    UseCase,
)
from amzn_nova_act_human_intervention_common.models.dynamodb_models import (
    ConnectionItem,
    ErrorCode,
    ErrorDetails,
    ExecutionItem,
    ExecutionStatus,
)
from amzn_nova_act_human_intervention_common.models.executor_models import ExecutorRequest
from amzn_nova_act_human_intervention_common.models.intervention_models import (
    BrowserSessionContext,
    InterventionContext,
)
from amzn_nova_act_human_intervention_common.models.request_models import (
    ApprovalAction,
    ApprovalOption,
    ApprovalRequest,
    UITakeoverRequest,
)
from amzn_nova_act_human_intervention_common.models.step_function_models import (
    ApprovalStepFunctionInput,
    StepFunctionInput,
    UITakeoverStepFunctionInput,
)
from amzn_nova_act_human_intervention_common.models.type_definitions import (
    GenericDict,
    InterventionRequest,
    JSONType,
)

# Rebuild models to resolve forward references
# This is required because ExecutorRequest uses InterventionRequest (a Union type)
# that references UITakeoverStepFunctionInput and ApprovalStepFunctionInput.
# Even with proper import order, Pydantic needs explicit rebuild to resolve
# the forward references in the Union type definition.
ExecutorRequest.model_rebuild()

# Rebuild ExecutionItem to ensure new fields (errorDetails) are recognized by mypy
ExecutionItem.model_rebuild()

__all__ = [
    # Workflow models
    "UseCase",
    "InterventionContext",
    "BrowserSessionContext",
    "StepFunctionInput",
    "UITakeoverStepFunctionInput",
    "ApprovalStepFunctionInput",
    "NotificationRecipient",
    "NotificationChannel",
    "SlackTargetType",
    "ContactInfo",
    "EmailContactInfo",
    "SlackContactInfo",
    "ExecutionStatus",
    "ExecutorRequest",
    "UITakeoverRequest",
    "ApprovalRequest",
    "ApprovalOption",
    "ApprovalAction",
    # DynamoDB models
    "ConnectionItem",
    "ExecutionItem",
    "ErrorCode",
    "ErrorDetails",
    # Type definitions
    "JSONType",
    "GenericDict",
    "InterventionRequest",
]
