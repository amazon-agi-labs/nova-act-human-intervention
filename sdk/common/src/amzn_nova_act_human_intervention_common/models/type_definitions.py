"""Type definitions for Nova Act Human Intervention.

This module defines type aliases used throughout the package for type safety
and consistency.

Type Aliases
------------
JSONType : TypeAliasType
    Recursive type representing JSON-serializable values for Lambda responses.
    Supports nested dictionaries, lists, and primitive types (str, int, float, bool, None).

    Examples:
        - Simple value: "hello" or 42 or True
        - List: ["item1", "item2", 3]
        - Nested dict: {"status": "success", "data": {"count": 10, "items": []}}

GenericDict : Dict[str, Any]
    Generic dictionary type for flexible key-value storage.
    Used when the structure is dynamic or varies by context.

    Examples:
        - {"key": "value", "count": 42}
        - {"metadata": {"timestamp": 1234567890}, "tags": ["tag1", "tag2"]}

InterventionRequest : Union[UITakeoverStepFunctionInput, ApprovalStepFunctionInput]
    Union type representing either UI Takeover or Approval intervention requests.
    Used for functions that accept any type of intervention workflow input.

    Examples:
        - UITakeoverStepFunctionInput instance for browser control interventions
        - ApprovalStepFunctionInput instance for approval decision interventions
"""

from typing import TYPE_CHECKING, Any, Dict, Union  # noqa: F401

from typing_extensions import TypeAliasType

if TYPE_CHECKING:
    from amzn_nova_act_human_intervention_common.models.step_function_models import (
        ApprovalStepFunctionInput,
        UITakeoverStepFunctionInput,
    )

# JSON-serializable types for Lambda responses
JSONType = TypeAliasType(
    "JSONType",
    "Union[dict[str, JSONType], list[JSONType], str, int, float, bool, None]",
)

# Dictionary type alias
GenericDict = Dict[str, Any]

# Step function input type alias
InterventionRequest = Union["UITakeoverStepFunctionInput", "ApprovalStepFunctionInput"]
