"""Tests for Lambda authorizer module."""

from unittest.mock import Mock, patch

from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

from amzn_nova_act_human_intervention.workflows.authorizer import (
    authorizer_handler,
    generate_policy,
    get_execution_item,
)


class TestAuthorizerHandler:
    """Minimal test coverage for authorizer_handler function."""

    def setup_method(self) -> None:
        self.context = Mock(spec=LambdaContext)
        self.method_arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/prod/POST/api/v1/task"

    def _create_event_data(self, auth_header: str | None = "Bearer test-token-123") -> dict:
        """Create event data dict for APIGatewayAuthorizerRequestEvent."""
        headers = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        return {
            "methodArn": self.method_arn,
            "headers": headers,
        }

    @patch("amzn_nova_act_human_intervention.workflows.authorizer.get_execution_item")
    def test_success_with_bearer_token(self, mock_get_item: Mock) -> None:
        mock_item = Mock()
        mock_item.eventId = "test-token-123"
        mock_item.workflowRunId = "wf-123"
        mock_item.sessionId = "sess-123"
        mock_item.actId = "act-123"
        mock_item.interventionType = "UITakeover"
        mock_get_item.return_value = mock_item

        event_data = self._create_event_data("Bearer test-token-123")
        result = authorizer_handler(event_data, self.context)

        assert result["principalId"] == "test-token-123"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert result["context"]["eventId"] == "test-token-123"
        mock_get_item.assert_called_once_with("test-token-123")

    @patch("amzn_nova_act_human_intervention.workflows.authorizer.get_execution_item")
    def test_missing_authorization_header(self, mock_get_item: Mock) -> None:
        event_data = self._create_event_data(None)
        result = authorizer_handler(event_data, self.context)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"
        mock_get_item.assert_not_called()

    @patch("amzn_nova_act_human_intervention.workflows.authorizer.get_execution_item")
    def test_token_not_found(self, mock_get_item: Mock) -> None:
        mock_get_item.return_value = None

        event_data = self._create_event_data("Bearer invalid-token")
        result = authorizer_handler(event_data, self.context)

        assert result["principalId"] == "invalid-token"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"
        mock_get_item.assert_called_once_with("invalid-token")


@patch.dict("os.environ", {"EXECUTIONS_TABLE": "test-executions-table"})
@patch("amzn_nova_act_human_intervention.workflows.authorizer.boto3")
class TestGetExecutionItem:
    """Minimal test coverage for get_execution_item function."""

    def test_success(self, mock_boto3: Mock) -> None:
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_boto3.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {
            "Item": {
                "eventId": "test-123",
                "workflowRunId": "wf-123",
                "sessionId": "sess-123",
                "actId": "act-123",
                "interventionType": "UITakeover",
                "executionStatus": "PENDING_HUMAN_INPUT",
                "connectionId": "conn-123",
                "executionArn": "arn:aws:states:us-west-2:123:execution:test",
                "timeout": 3600,
                "notificationRecipients": [],
                "createdAt": 1234567890,
                "updatedAt": 1234567890,
                "ttl": 1234567890,
                "executionEndpoint": "wss://test.execute-api.us-west-2.amazonaws.com/prod",
            }
        }

        result = get_execution_item("test-123")

        assert result is not None
        assert result.eventId == "test-123"
        mock_table.get_item.assert_called_once_with(Key={"eventId": "test-123"})

    def test_not_found(self, mock_boto3: Mock) -> None:
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_boto3.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        mock_table.get_item.return_value = {}

        result = get_execution_item("nonexistent-123")

        assert result is None

    def test_client_error(self, mock_boto3: Mock) -> None:
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_boto3.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        error_response = {"Error": {"Message": "Table not found", "Code": "ResourceNotFoundException"}}
        mock_table.get_item.side_effect = ClientError(error_response, "GetItem")

        result = get_execution_item("test-123")

        assert result is None


class TestGeneratePolicy:
    """Minimal test coverage for generate_policy function."""

    def test_allow_policy_without_context(self) -> None:
        result = generate_policy("user-123", "Allow", "arn:aws:execute-api:us-west-2:123:api/*/*/*")

        assert result["principalId"] == "user-123"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert "context" not in result

    def test_deny_policy(self) -> None:
        result = generate_policy("user-123", "Deny", "arn:aws:execute-api:us-west-2:123:api/*/*/*")

        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_with_context(self) -> None:
        context = {"eventId": "event-123", "workflowRunId": "wf-123"}

        result = generate_policy("user-123", "Allow", "arn:aws:execute-api:us-west-2:123:api/*/*/*", context)

        assert result["context"]["eventId"] == "event-123"
        assert result["context"]["workflowRunId"] == "wf-123"


class TestAuthorizerHandlerAdditional:
    """Additional test coverage for authorizer_handler edge cases."""

    def setup_method(self) -> None:
        self.context = Mock(spec=LambdaContext)
        self.method_arn = "arn:aws:execute-api:us-west-2:123456789012:abcdef123/prod/POST/api/v1/task"

    @patch("amzn_nova_act_human_intervention.workflows.authorizer.get_execution_item")
    def test_empty_token_after_bearer(self, mock_get_item: Mock) -> None:
        """Test with Bearer prefix but empty token."""
        event_data = {
            "methodArn": self.method_arn,
            "headers": {"Authorization": "Bearer "},
        }
        result = authorizer_handler(event_data, self.context)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"
        mock_get_item.assert_not_called()

    @patch("amzn_nova_act_human_intervention.workflows.authorizer.get_execution_item")
    def test_exception_in_handler(self, mock_get_item: Mock) -> None:
        """Test exception handling in authorizer_handler."""
        mock_get_item.side_effect = Exception("Unexpected error")

        event_data = {
            "methodArn": self.method_arn,
            "headers": {"Authorization": "Bearer test-token"},
        }
        result = authorizer_handler(event_data, self.context)

        assert result["principalId"] == "user"
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"


@patch.dict("os.environ", {}, clear=True)
@patch("amzn_nova_act_human_intervention.workflows.authorizer.boto3")
class TestGetExecutionItemMissingEnv:
    """Test get_execution_item with missing environment variable."""

    def test_missing_executions_table_env(self, mock_boto3: Mock) -> None:
        """Test with missing EXECUTIONS_TABLE environment variable."""
        result = get_execution_item("test-123")

        assert result is None
        mock_boto3.resource.assert_not_called()


@patch.dict("os.environ", {"EXECUTIONS_TABLE": "test-executions-table"})
@patch("amzn_nova_act_human_intervention.workflows.authorizer.boto3")
class TestGetExecutionItemAdditional:
    """Additional test coverage for get_execution_item edge cases."""

    def test_generic_exception(self, mock_boto3: Mock) -> None:
        """Test with generic exception during execution item retrieval."""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_boto3.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        # Simulate a generic exception (not ClientError)
        mock_table.get_item.side_effect = Exception("Unexpected error")

        result = get_execution_item("test-123")

        assert result is None
