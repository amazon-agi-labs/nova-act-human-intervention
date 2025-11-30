"""Response models for Lambda handlers."""

import json
from http import HTTPStatus
from typing import Dict

from amzn_nova_act_human_intervention_common import JSONType
from pydantic import BaseModel


class LambdaResponse(BaseModel):
    """Unified Lambda response builder for all invocation types.

    Provides a consistent structure for Lambda handler responses across
    WebSocket, DynamoDB Stream, and Step Function handlers. API Gateway
    REST endpoints require special formatting with headers and JSON-encoded body.

    Attributes:
        status_code: HTTP status code (200 for success, 4xx/5xx for errors)
        body: Response body content (string, dict, or None)

    Example:
        >>> # Success with message
        >>> response = LambdaResponse.success(body="Task completed")
        >>> response.for_lambda()
        {"statusCode": 200, "body": "Task completed"}

        >>> # Error with message
        >>> response = LambdaResponse.error(500, body="Internal error")
        >>> response.for_lambda()
        {"statusCode": 500, "body": "Internal error"}

        >>> # Success with dict body
        >>> response = LambdaResponse.success(body={"event_id": "123", "status": "done"})
        >>> response.for_lambda()
        {"statusCode": 200, "body": {"event_id": "123", "status": "done"}}

        >>> # API Gateway format
        >>> response = LambdaResponse.success(body={"message": "Success"})
        >>> response.for_api_gateway()
        {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": '{"message": "Success"}'
        }
    """

    status_code: int
    body: str | JSONType | None = None

    @classmethod
    def success(cls, body: str | JSONType | None = None) -> "LambdaResponse":
        """Create a successful response with HTTP 200 status.

        Args:
            body: Optional response body (string or dict)

        Returns:
            LambdaResponse with status_code=200
        """
        return cls(status_code=HTTPStatus.OK, body=body)

    @classmethod
    def error(cls, status_code: int, body: str | JSONType | None = None) -> "LambdaResponse":
        """Create an error response with specified status code.

        Args:
            status_code: HTTP error status code (4xx or 5xx)
            body: Optional error message or details

        Returns:
            LambdaResponse with the specified error status code
        """
        return cls(status_code=status_code, body=body)

    def for_api_gateway(self, cors: bool = True) -> JSONType:
        """Format response for API Gateway REST endpoints.

        API Gateway requires:
        - headers dict with Content-Type and CORS headers
        - body as JSON-encoded string (not raw dict)

        Args:
            cors: Whether to include CORS headers (default: True)

        Returns:
            Dict with statusCode, headers, and JSON-encoded body
        """
        headers: Dict[str, JSONType] = {"Content-Type": "application/json"}
        if cors:
            headers["Access-Control-Allow-Origin"] = "*"

        # Ensure body is a dict for JSON encoding
        body_content = self.body if isinstance(self.body, dict) else {"message": self.body}

        return {"statusCode": self.status_code, "headers": headers, "body": json.dumps(body_content)}

    def for_lambda(self) -> JSONType:
        """Format response for WebSocket, Stream, and Step Function handlers.

        Returns standardized structure for success/error reporting.
        All non-API Gateway Lambda handlers use this format.

        Returns:
            Dict with statusCode and body fields
        """
        return {"statusCode": self.status_code, "body": self.body}
