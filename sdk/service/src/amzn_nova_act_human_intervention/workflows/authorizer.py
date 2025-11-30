"""Lambda authorizer for validating eventId tokens against DynamoDB.

This authorizer validates tokens (eventId) from the Authorization header
and generates IAM policies for API Gateway access control.
"""

import os
from typing import Dict

import boto3
from amzn_nova_act_human_intervention_common import ExecutionItem, GenericDict, LoggingConfig
from aws_lambda_powertools.utilities.data_classes import event_source
from aws_lambda_powertools.utilities.data_classes.api_gateway_authorizer_event import APIGatewayAuthorizerRequestEvent
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

logger = LoggingConfig.get_logger(__name__)


@event_source(data_class=APIGatewayAuthorizerRequestEvent)
def authorizer_handler(event: APIGatewayAuthorizerRequestEvent, context: LambdaContext) -> GenericDict:
    """Lambda authorizer for API Gateway.

    Validates the token (eventId) from the Authorization header against DynamoDB
    and returns an IAM policy allowing or denying access.

    Args:
        event: API Gateway authorizer request event
        context: Lambda context

    Returns:
        IAM policy document with Allow or Deny effect

    Example event:
        {
            "type": "REQUEST",
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/api-name",
            "headers": {
                "Authorization": "Bearer e4b232ed-ddc6-40bf-b61f-4e62da0c3f2a"
            },
            ...
        }

    Example response (Allow):
        {
            "principalId": "e4b232ed-ddc6-40bf-b61f-4e62da0c3f2a",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/POST/*"
                }]
            },
            "context": {
                "eventId": "e4b232ed-ddc6-40bf-b61f-4e62da0c3f2a",
                "workflowRunId": "550e8400-e29b-41d4-a716-446655440000",
                "sessionId": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
            }
        }
    """
    try:
        logger.info(f"Authorizer invoked for method ARN: {event.method_arn}")

        # Extract token from Authorization header
        # Expected format: "Bearer <eventId>" or just "<eventId>"
        auth_header = event.headers.get("Authorization") or event.headers.get("authorization")

        if not auth_header:
            logger.warning(f"No Authorization header found. Headers: {event.headers}")
            return generate_policy("user", "Deny", event.method_arn)

        # Remove "Bearer " prefix if present
        token = auth_header.replace("Bearer ", "").strip()
        logger.info(f"Extracted token from Authorization header: {token[:8]}...")

        if not token:
            logger.warning("Empty token in Authorization header")
            return generate_policy("user", "Deny", event.method_arn)

        # Validate token against DynamoDB
        execution_item: ExecutionItem | None = get_execution_item(token)

        if not execution_item:
            logger.warning(f"Authorization denied: Token not found in DynamoDB: {token}")
            return generate_policy(token, "Deny", event.method_arn)

        # Generate Allow policy with context
        # Extract the API Gateway ARN base (everything before the HTTP method)
        # From: arn:aws:execute-api:region:account:api-id/stage/METHOD/path
        # To:   arn:aws:execute-api:region:account:api-id/stage/*/*
        method_arn = event.method_arn
        arn_parts = method_arn.split("/")
        api_gateway_base = "/".join(arn_parts[:2])  # arn:aws:execute-api:...:api-id/stage
        resource_arn = f"{api_gateway_base}/*/*"  # Allow all methods and paths

        policy = generate_policy(
            principal_id=token,
            effect="Allow",
            resource=resource_arn,
            context={
                "eventId": execution_item.eventId,
                "workflowRunId": execution_item.workflowRunId,
                "sessionId": execution_item.sessionId,
                "actId": execution_item.actId,
                "interventionType": execution_item.interventionType,
            },
        )

        logger.info(f"Authorization successful for token: {token}")
        return policy

    except Exception as e:
        logger.exception(f"Error in authorizer: {str(e)}")
        return generate_policy("user", "Deny", event.method_arn)


def get_execution_item(event_id: str) -> ExecutionItem | None:
    """Retrieve execution item from DynamoDB.

    Args:
        event_id: Event ID to look up

    Returns:
        Execution item dict if found, None otherwise
    """
    table_name = os.environ.get("EXECUTIONS_TABLE")
    if not table_name:
        logger.error("EXECUTIONS_TABLE environment variable not set")
        return None

    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)
        response = table.get_item(Key={"eventId": event_id})

        item = response.get("Item")
        if not item:
            logger.warning(f"No item found in DynamoDB for eventId: {event_id}")
            return None

        logger.info(f"Found execution item for eventId: {event_id}")
        return ExecutionItem(**item)

    except ClientError as e:
        logger.error(f"DynamoDB error for eventId {event_id}: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        logger.exception(f"Error retrieving execution item for eventId {event_id}: {str(e)}")
        return None


def generate_policy(
    principal_id: str, effect: str, resource: str, context: Dict[str, str] | None = None
) -> GenericDict:
    """Generate IAM policy document.

    Args:
        principal_id: The principal user identification (typically the eventId)
        effect: "Allow" or "Deny"
        resource: The ARN of the resource to allow/deny
        context: Optional context to pass to the Lambda function

    Returns:
        IAM policy document
    """
    policy = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{"Action": "execute-api:Invoke", "Effect": effect, "Resource": resource}],
        },
    }

    # Add context if provided (will be available in Lambda as event.requestContext.authorizer)
    if context:
        # API Gateway authorizer context values must be strings
        policy["context"] = {k: str(v) for k, v in context.items()}

    return policy
