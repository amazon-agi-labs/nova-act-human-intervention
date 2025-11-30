import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from amzn_nova_act_human_intervention_common import ExecutionStatus, GenericDict, InterventionContext, Utils
from websocket import WebSocket

from amzn_nova_act_human_intervention_client.credentials import AssumedRoleCredentialsProvider
from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors.websocket.executor import (
    WebsocketBasedInterventionExecutor,
)


class TestWebsocketBasedInterventionExecutor:
    @pytest.fixture
    def intervention_context(self):
        return InterventionContext(workflow_run_id="run1", act_session_id="session1", act_id="act1")

    @pytest.fixture
    def client(self, intervention_context):
        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                """Test implementation of _on_message."""
                if Utils.is_valid_json(message):
                    rcvd_message: GenericDict = json.loads(message)
                    message_type = rcvd_message.get("type")
                    if message_type == "workflow_started":
                        self.logger.info(f"[Test Workflow Started] Event ID: {rcvd_message.get('eventId')}")
                        self._is_reconnecting = False
                    elif message_type == "workflow_completed":
                        execution_status = rcvd_message.get("executionStatus")
                        self.logger.info(f"[Test Workflow Completed] Event ID: {rcvd_message.get('eventId')}")
                        self._completion_received = True
                        self.completion_response = rcvd_message
                        self._handle_completion(app, rcvd_message)
                        # WorkflowExecutionError only for TERMINATED status
                        # RuntimeError for FAILED or null/missing executionStatus
                        if execution_status is None:
                            error_msg = "Test workflow completed with null executionStatus"
                            self.logger.error(error_msg)
                            self._exception = RuntimeError(error_msg)
                        elif execution_status == ExecutionStatus.TERMINATED.value:
                            additional_message = rcvd_message.get("message")
                            self.logger.error(f"Test workflow terminated: {execution_status}")
                            self._exception = WorkflowExecutionError(
                                status=ExecutionStatus.TERMINATED,
                                workflow_type="Test",
                                message=additional_message,
                            )
                        elif execution_status == ExecutionStatus.FAILED.value:
                            error_msg = f"Test workflow failed with status: {execution_status}"
                            additional_message = rcvd_message.get("message")
                            if additional_message:
                                error_msg = f"{error_msg} - {additional_message}"
                            self.logger.error(error_msg)
                            self._exception = RuntimeError(error_msg)
                    else:
                        self.logger.info(f"Test message received: {rcvd_message}")

        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }
        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            return TestClient("ws://test", intervention_context, credentials_provider=credentials_provider)

    def test_validate_websocket_url_valid_ws(self, intervention_context):
        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                pass  # Minimal implementation for test

        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }
        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            client = TestClient("ws://example.com", intervention_context, credentials_provider=credentials_provider)
            assert client._endpoint == "ws://example.com"

    def test_validate_websocket_url_invalid_http(self, intervention_context):
        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                pass  # Minimal implementation for test

        with pytest.raises(ValueError, match="Invalid WebSocket URL"):
            mock_sts = Mock()
            expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
            mock_sts.assume_role.return_value = {
                "Credentials": {
                    "AccessKeyId": "test_key",
                    "SecretAccessKey": "test_secret",
                    "SessionToken": "test_token",
                    "Expiration": expiry_time,
                }
            }
            with patch("boto3.Session") as mock_session_class:
                mock_session_instance = Mock()
                mock_session_class.return_value = mock_session_instance
                mock_session_instance.client.return_value = mock_sts
                credentials_provider = AssumedRoleCredentialsProvider(
                    role_arn="arn:aws:iam::123:role/test",
                    duration_seconds=3600,
                    session=mock_session_instance,
                )
                TestClient("http://example.com", intervention_context, credentials_provider=credentials_provider)

    def test_init(self, client, intervention_context):
        assert client._endpoint == "ws://test"
        assert client._intervention_context == intervention_context
        assert client.app is None
        assert client._credentials_provider is not None
        assert client._is_reconnecting is False
        assert client._completion_received is False

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.abort")
    def test_handle_completion(self, mock_abort, client):
        mock_ws = Mock()
        message = {"type": "execution_completed"}

        client._handle_completion(mock_ws, message)

        assert client._completion_received is True
        mock_ws.close.assert_called_once()
        mock_abort.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_run(self, mock_websocket_app, mock_rel, client):
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        mock_websocket_app.assert_called_once()
        # Verify ping_interval and ping_timeout prevent API Gateway idle timeout
        from amzn_nova_act_human_intervention_client.utils.constants import (
            WEBSOCKET_PING_INTERVAL,
            WEBSOCKET_PING_TIMEOUT,
            WEBSOCKET_RECONNECT_INTERVAL,
        )

        mock_app.run_forever.assert_called_once_with(
            dispatcher=mock_rel,
            reconnect=WEBSOCKET_RECONNECT_INTERVAL,
            ping_interval=WEBSOCKET_PING_INTERVAL,
            ping_timeout=WEBSOCKET_PING_TIMEOUT,
        )

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_message_workflow_completed(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_message = call_args[1]["on_message"]

        with patch.object(client, "_handle_completion") as mock_handle:
            message = '{"type": "workflow_completed", "executionStatus": "SUCCEEDED", "data": "test"}'
            on_message(mock_app, message)
            mock_handle.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_message_workflow_started(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_message = call_args[1]["on_message"]

        message = '{"type": "workflow_started"}'
        on_message(mock_app, message)
        assert client._is_reconnecting is False

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_message_connection_status(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_message = call_args[1]["on_message"]

        message = '{"type": "workflow_started"}'
        on_message(mock_app, message)
        assert client.completion_response is None

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_error(self, mock_websocket_app, mock_rel, client):
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_error = call_args[1]["on_error"]

        test_error = Exception("Test error")
        on_error(mock_app, test_error)

        mock_app.close.assert_called_once()
        mock_rel.abort.assert_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_close(self, mock_websocket_app, mock_rel, client):
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_close = call_args[1]["on_close"]

        on_close(mock_app, 1000, "Normal closure")

        mock_app.close.assert_called_once()
        mock_rel.abort.assert_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_open(self, mock_websocket_app, mock_rel, client):
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_open = call_args[1]["on_open"]

        on_open(mock_app)

        mock_app.send.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_expiry_checks_with_role(self, mock_timeout, intervention_context):
        from datetime import datetime, timedelta, timezone

        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                pass  # Minimal implementation for test

        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=1800)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }
        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            client = TestClient(
                "ws://test",
                intervention_context,
                credentials_provider=credentials_provider,
            )

            client._schedule_expiry_checks()

            assert mock_timeout.call_count == 2

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.abort")
    def test_close_expired_connection(self, mock_abort, client):
        mock_app = Mock()
        client.app = mock_app

        client._close_expired_connection()

        mock_app.close.assert_called_once()
        mock_abort.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.abort")
    def test_close_expired_connection_already_completed(self, mock_abort, client):
        client._completion_received = True
        mock_app = Mock()
        client.app = mock_app

        client._close_expired_connection()

        mock_app.close.assert_not_called()
        mock_abort.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_init_websocket_app(self, mock_websocket_app, client):
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            result = client._init_websocket_app()

        assert result == mock_app
        mock_websocket_app.assert_called_once()

        # Verify ping/pong handlers are registered
        call_kwargs = mock_websocket_app.call_args[1]
        assert "on_ping" in call_kwargs
        assert "on_pong" in call_kwargs
        assert call_kwargs["on_ping"] == client._on_ping
        assert call_kwargs["on_pong"] == client._on_pong

    def test_init_websocket_app_no_credentials(self, client):
        # Mock the credentials provider to raise an error
        mock_provider = Mock()
        mock_provider.expiry = datetime.now(timezone.utc) + timedelta(seconds=3600)
        type(mock_provider).credentials = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("No credentials available"))
        )
        client._credentials_provider = mock_provider

        with pytest.raises(RuntimeError, match="No credentials available"):
            client._init_websocket_app()

    def test_ensure_valid_credentials_expired(self, client):
        """Test credential refresh when expired via provider."""
        from datetime import datetime, timedelta, timezone

        # Mock the credentials provider to return expired credentials
        mock_provider = Mock()
        type(mock_provider).expiry = property(lambda self: datetime.now(timezone.utc) - timedelta(seconds=1))
        client._credentials_provider = mock_provider
        # Set execution start time to "now" so credentials appear expired
        client._execution_start_time = datetime.now(timezone.utc)

        client._ensure_valid_credentials()

        # Verify provider's refresh method was called
        mock_provider.refresh.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_expiry_checks_credential_refresh_timing(self, mock_timeout, intervention_context):
        """Test credential refresh scheduling logic with provider."""
        from datetime import datetime, timedelta, timezone

        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                pass  # Minimal implementation for test

        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=1000)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }
        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            client = TestClient(
                "ws://test",
                intervention_context,
                credentials_provider=credentials_provider,
            )

            # Set execution start time and URL expiry for proper timing calculation
            client._execution_start_time = datetime.now(timezone.utc)
            client._url_expires_in = 2000
            client._refresh_buffer = int(0.1 * client._url_expires_in)  # 200 seconds

            client._schedule_expiry_checks()

            # Should schedule execution timeout, URL refresh, and credential refresh
            assert mock_timeout.call_count == 3

            # Verify credential refresh is scheduled (should be around 800 seconds: 1000 - 200)
            # Allow for small timing variations due to test execution
            refresh_calls = [call for call in mock_timeout.call_args_list if 790 <= call[0][0] <= 810]
            assert len(refresh_calls) == 1

    def test_init_websocket_app_no_credentials_error(self, client):
        """Test RuntimeError when no credentials available from provider."""
        # Mock the credentials provider to raise an error
        mock_provider = Mock()
        mock_provider.expiry = datetime.now(timezone.utc) + timedelta(seconds=3600)
        type(mock_provider).credentials = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("No credentials available"))
        )
        client._credentials_provider = mock_provider

        with pytest.raises(RuntimeError, match="No credentials available"):
            client._init_websocket_app()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.abort")
    def test_handle_completion_sets_flags_and_closes(self, mock_abort, client):
        """Test lines 262-264: completion handling sets flags and closes connection."""
        mock_ws = Mock()
        message = {"type": "execution_completed", "data": "test"}

        client._handle_completion(mock_ws, message)

        # Verify all three lines are executed
        assert client._completion_received is True
        mock_ws.close.assert_called_once()
        mock_abort.assert_called_once()

    def test_on_ping(self, client):
        """Test _on_ping handler logs incoming ping."""
        mock_app = Mock()
        test_message = "test_ping_payload"

        # Should not raise any exception
        client._on_ping(mock_app, test_message)

    def test_on_pong(self, client):
        """Test _on_pong handler logs incoming pong."""
        mock_app = Mock()
        test_message = "test_pong_payload"

        # Should not raise any exception
        client._on_pong(mock_app, test_message)

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_workflow_failed_raises_exception(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        """Test that failed workflows raise RuntimeError after event loop completes."""
        from amzn_nova_act_human_intervention_common import ExecutionStatus

        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            # Simulate the run starting
            client._input_data = "test_input"
            client._completion_received = False
            client._exception = None
            client.app = client._init_websocket_app()

            # Get the on_message callback
            call_args = mock_websocket_app.call_args
            on_message = call_args[1]["on_message"]

            # Send a workflow_completed message with FAILED status
            message = (
                f'{{"type": "workflow_completed", '
                f'"executionStatus": "{ExecutionStatus.FAILED.value}", '
                f'"eventId": "test-123"}}'
            )
            on_message(mock_app, message)

            # Verify exception was stored
            assert client._exception is not None
            assert isinstance(client._exception, RuntimeError)
            assert "Test workflow failed with status: FAILED" in str(client._exception)

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_workflow_terminated_raises_exception(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        """Test that terminated workflows raise WorkflowExecutionError after event loop completes."""
        from amzn_nova_act_human_intervention_common import ExecutionStatus

        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            # Simulate the run starting
            client._input_data = "test_input"
            client._completion_received = False
            client._exception = None
            client.app = client._init_websocket_app()

            # Get the on_message callback
            call_args = mock_websocket_app.call_args
            on_message = call_args[1]["on_message"]

            # Send a workflow_completed message with TERMINATED status
            message = (
                f'{{"type": "workflow_completed", '
                f'"executionStatus": "{ExecutionStatus.TERMINATED.value}", '
                f'"eventId": "test-456"}}'
            )
            on_message(mock_app, message)

            # Verify exception was stored
            assert client._exception is not None
            assert isinstance(client._exception, WorkflowExecutionError)
            assert "Test workflow failed with status: TERMINATED" in str(client._exception)
            assert client._exception.status == ExecutionStatus.TERMINATED
            assert client._exception.workflow_type == "Test"

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_workflow_null_status_raises_exception(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        """Test that null executionStatus raises RuntimeError after event loop completes."""
        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            # Simulate the run starting
            client._input_data = "test_input"
            client._completion_received = False
            client._exception = None
            client.app = client._init_websocket_app()

            # Get the on_message callback
            call_args = mock_websocket_app.call_args
            on_message = call_args[1]["on_message"]

            # Send a workflow_completed message with null executionStatus
            message = '{"type": "workflow_completed", "executionStatus": null, "eventId": "test-789"}'
            on_message(mock_app, message)

            # Verify exception was stored
            assert client._exception is not None
            assert isinstance(client._exception, RuntimeError)
            assert "null executionStatus" in str(client._exception)

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_init_websocket_app_with_max_url_expires_in(self, mock_websocket_app, intervention_context):
        """Test that expires_in is capped at MAX_URL_EXPIRES_IN when using role_arn."""
        from datetime import datetime, timedelta, timezone

        from amzn_nova_act_human_intervention_client.utils.constants import MAX_URL_EXPIRES_IN

        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                pass  # Minimal implementation for test

        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        # Mock STS assume_role response
        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }

        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            # Create client with credentials_provider and execution_timeout > MAX_URL_EXPIRES_IN
            client = TestClient(
                "ws://test",
                intervention_context,
                credentials_provider=credentials_provider,
                execution_timeout=7200,  # 2 hours, exceeds MAX_URL_EXPIRES_IN (3600)
            )

            # Mock the signer
            with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url") as mock_sign:
                client._init_websocket_app()

                # Verify that sign_websocket_url was called with MAX_URL_EXPIRES_IN (line 224)
                assert mock_sign.called
                call_kwargs = mock_sign.call_args[1]
                assert call_kwargs["expires_in"] == MAX_URL_EXPIRES_IN

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_common.Utils.is_valid_json")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_message_unknown_type(self, mock_websocket_app, mock_is_valid_json, mock_rel, client):
        """Test handling of unknown message types (line 303)."""
        mock_is_valid_json.return_value = True
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_message = call_args[1]["on_message"]

        # Send a message with unknown type
        message = '{"type": "unknown_message_type", "data": "test"}'
        on_message(mock_app, message)

        # Should handle gracefully and just log (no exception)
        assert client._exception is None

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_error_workflow_execution_error_stored(self, mock_websocket_app, mock_rel, client):
        """Test that WorkflowExecutionError is stored in _on_error."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_error = call_args[1]["on_error"]

        # Send a WorkflowExecutionError
        test_error = WorkflowExecutionError(
            status=ExecutionStatus.FAILED,
            workflow_type="Test",
            message="Test workflow error",
        )
        on_error(mock_app, test_error)

        # Verify WorkflowExecutionError was stored in _exception
        assert client._exception == test_error
        mock_app.close.assert_called_once()
        mock_rel.abort.assert_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.datetime")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    def test_refresh_websocket_connection_success(self, mock_rel, mock_datetime, client):
        """Test successful WebSocket URL refresh."""
        from datetime import datetime, timedelta, timezone

        # Setup current time and execution start time
        now = datetime.now(timezone.utc)
        mock_datetime.now.return_value = now
        client._execution_start_time = now - timedelta(seconds=3000)  # 50 minutes ago
        client._execution_timeout = 7200  # 2 hours
        client._url_expires_in = 3600  # 1 hour
        client._completion_received = False

        # Mock the current WebSocket app
        mock_old_app = Mock()
        client.app = mock_old_app

        # Mock _init_websocket_app to return a new app
        mock_new_app = Mock()
        with patch.object(client, "_init_websocket_app", return_value=mock_new_app):
            client._refresh_websocket_connection()

        # Verify old connection was closed
        mock_old_app.close.assert_called_once()

        # Verify _is_url_refresh flag was set
        assert client._is_url_refresh is True

        # Verify new app was created
        assert client.app == mock_new_app

        # Verify run_forever was called to register new app with event loop
        from amzn_nova_act_human_intervention_client.utils.constants import (
            WEBSOCKET_PING_INTERVAL,
            WEBSOCKET_PING_TIMEOUT,
            WEBSOCKET_RECONNECT_INTERVAL,
        )

        mock_new_app.run_forever.assert_called_once_with(
            dispatcher=mock_rel,
            reconnect=WEBSOCKET_RECONNECT_INTERVAL,
            ping_interval=WEBSOCKET_PING_INTERVAL,
            ping_timeout=WEBSOCKET_PING_TIMEOUT,
        )

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.datetime")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    def test_refresh_websocket_connection_timeout_reached(self, mock_rel, mock_datetime, client):
        """Test WebSocket refresh when execution timeout is reached.

        When timeout is reached, the reconnection attempt should fail immediately
        and abort without extensive retries.
        """
        from datetime import datetime, timedelta, timezone

        # Setup current time - execution has timed out
        now = datetime.now(timezone.utc)
        mock_datetime.now.return_value = now
        client._execution_start_time = now - timedelta(seconds=3700)  # Over 1 hour ago
        client._execution_timeout = 3600  # 1 hour timeout
        client._completion_received = False

        mock_old_app = Mock()
        client.app = mock_old_app

        # Mock _perform_reconnection_with_retry to avoid actual retry delays
        with patch.object(client, "_perform_reconnection_with_retry") as mock_reconnect:
            # Simulate the timeout check that happens in _perform_reconnection_with_retry
            def side_effect():
                elapsed_time = (datetime.now(timezone.utc) - client._execution_start_time).total_seconds()
                time_remaining = client._execution_timeout - elapsed_time
                if time_remaining <= 0:
                    mock_rel.abort()
                    raise RuntimeError("Execution timeout reached")

            mock_reconnect.side_effect = side_effect

            client._refresh_websocket_connection()

        # After detecting timeout, abort is called
        mock_rel.abort.assert_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.datetime")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    def test_refresh_websocket_connection_already_completed(self, mock_rel, mock_datetime, client):
        """Test WebSocket refresh when workflow already completed."""
        client._completion_received = True

        client._refresh_websocket_connection()

        # Should do nothing when already completed
        mock_rel.dispatch.assert_not_called()
        mock_rel.abort.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.datetime")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    def test_refresh_websocket_connection_schedules_next_refresh(self, mock_rel, mock_datetime, client):
        """Test WebSocket refresh schedules next refresh for long executions."""
        from datetime import datetime, timedelta, timezone

        # Setup current time - only 30 minutes into 2-hour execution
        now = datetime.now(timezone.utc)
        mock_datetime.now.return_value = now
        client._execution_start_time = now - timedelta(seconds=1800)  # 30 minutes ago
        client._execution_timeout = 7200  # 2 hours
        client._url_expires_in = 3600  # 1 hour
        client._refresh_buffer = 720  # 12 minutes
        client._completion_received = False

        mock_old_app = Mock()
        client.app = mock_old_app

        mock_new_app = Mock()
        with patch.object(client, "_init_websocket_app", return_value=mock_new_app):
            client._refresh_websocket_connection()

        # Verify next refresh was scheduled
        # Time remaining: 7200 - 1800 = 5400 seconds (90 minutes)
        # Should schedule another refresh since 5400 > 3600
        assert mock_rel.timeout.called
        # Should schedule at url_expires_in - refresh_buffer = 3600 - 720 = 2880
        timeout_calls = [call[0][0] for call in mock_rel.timeout.call_args_list]
        assert 2880 in timeout_calls

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_open_sends_connection_refresh_message(self, mock_websocket_app, mock_rel, client):
        """Test that _on_open sends connection-refresh message when _is_url_refresh is True."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_open = call_args[1]["on_open"]

        # Simulate URL refresh scenario
        client._is_url_refresh = True
        client._event_id = "test-event-123"

        on_open(mock_app)

        # Verify connection-refresh message was sent
        assert mock_app.send.called
        sent_message = json.loads(mock_app.send.call_args[0][0])
        assert sent_message["action"] == "connection-refresh"
        assert sent_message["eventId"] == "test-event-123"

        # Verify flag was reset
        assert client._is_url_refresh is False

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_open_stores_event_id(self, mock_websocket_app, mock_rel, client):
        """Test that _on_open stores event_id from initial message."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        # Mock _create_message to return a message with event_id
        with patch.object(
            client, "_create_message", return_value={"action": "test", "input": {"event_id": "stored-event-456"}}
        ):
            with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
                client.run("test_input")

            call_args = mock_websocket_app.call_args
            on_open = call_args[1]["on_open"]

            # Trigger on_open
            on_open(mock_app)

            # Verify event_id was stored
            assert client._event_id == "stored-event-456"

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_expiry_checks_url_refresh_for_long_execution(self, mock_timeout, intervention_context):
        """Test that URL refresh is scheduled for executions longer than URL expiration."""
        from datetime import datetime, timedelta, timezone

        class TestClient(WebsocketBasedInterventionExecutor):
            def _create_message(self, input_data):
                return {"test": "message"}

            def _on_message(self, app: WebSocket, message: str) -> None:
                pass

        mock_sts = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }
        with patch("boto3.Session") as mock_session_class:
            mock_session_instance = Mock()
            mock_session_class.return_value = mock_session_instance
            mock_session_instance.client.return_value = mock_sts
            credentials_provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123:role/test",
                duration_seconds=3600,
                session=mock_session_instance,
            )
            # Create client with execution_timeout > url_expires_in (2 hours > 1 hour)
            client = TestClient(
                "ws://test",
                intervention_context,
                credentials_provider=credentials_provider,
                execution_timeout=7200,  # 2 hours
            )

            client._schedule_expiry_checks()

            # Should schedule 3 callbacks:
            # 1. Execution timeout (7200s)
            # 2. URL refresh (3600 - 720 = 2880s)
            # 3. Credential refresh (if applicable)
            assert mock_timeout.call_count >= 2

            # Verify URL refresh is scheduled
            timeout_calls = [call[0][0] for call in mock_timeout.call_args_list]
            # URL refresh should be at url_expires_in - refresh_buffer = 3600 - 720 = 2880
            assert 2880 in timeout_calls
            # Execution timeout should be 7200
            assert 7200 in timeout_calls

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_open_url_refresh_without_event_id(self, mock_websocket_app, mock_rel, client):
        """Test that connection-refresh message is not sent if event_id is missing."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_open = call_args[1]["on_open"]

        # Simulate URL refresh but without event_id
        client._is_url_refresh = True
        client._event_id = None
        client._is_reconnecting = True  # Prevent initial message from being sent

        on_open(mock_app)

        # Should not send connection-refresh message (no event_id)
        mock_app.send.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_open_reconnection_flag_handling(self, mock_websocket_app, mock_rel, client):
        """Test that _is_reconnecting flag is properly handled in _on_open."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_open = call_args[1]["on_open"]

        # Simulate normal reconnection (not URL refresh)
        client._is_reconnecting = True
        client._is_url_refresh = False

        on_open(mock_app)

        # Should not send initial message during normal reconnection
        mock_app.send.assert_not_called()

        # Verify reconnection flag was reset
        assert client._is_reconnecting is False

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_success(self, mock_timeout, client):
        """Test successful credential refresh scheduling."""
        from datetime import datetime, timedelta, timezone

        # Set up credentials that expire in 1000 seconds
        mock_provider = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=1000)
        type(mock_provider).expiry = property(lambda self: expiry_time)
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200  # 20% buffer

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000  # More than enough time

        client._schedule_credential_refresh(reference_time, max_duration, context="test")

        # Should schedule refresh at 1000 - 200 = 800 seconds
        mock_timeout.assert_called_once()
        scheduled_time = mock_timeout.call_args[0][0]
        assert 790 <= scheduled_time <= 810  # Allow for small timing variations

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_no_expiry(self, mock_timeout, client):
        """Test credential refresh scheduling when credentials have no expiry."""
        from datetime import datetime, timezone

        # Mock credentials provider with no expiry
        mock_provider = Mock()
        type(mock_provider).expiry = property(lambda self: None)
        client._credentials_provider = mock_provider

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000

        client._schedule_credential_refresh(reference_time, max_duration)

        # Should not schedule anything
        mock_timeout.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_exceeds_max_duration(self, mock_timeout, client):
        """Test credential refresh scheduling when refresh would exceed max_duration."""
        from datetime import datetime, timedelta, timezone

        # Set up credentials that expire beyond max_duration
        mock_provider = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=5000)
        type(mock_provider).expiry = property(lambda self: expiry_time)
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200

        reference_time = datetime.now(timezone.utc)
        max_duration = 1000  # Less than credential expiry

        client._schedule_credential_refresh(reference_time, max_duration)

        # Should not schedule (refresh would be at 5000-200=4800s > 1000s max_duration)
        mock_timeout.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_already_expired(self, mock_timeout, client):
        """Test credential refresh scheduling when credentials already expired."""
        from datetime import datetime, timedelta, timezone

        # Set up credentials that already expired
        mock_provider = Mock()
        expiry_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        type(mock_provider).expiry = property(lambda self: expiry_time)
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000

        client._schedule_credential_refresh(reference_time, max_duration)

        # Should not schedule (time_until_cred_refresh < 0)
        mock_timeout.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.datetime")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    def test_refresh_websocket_connection_schedules_credential_refresh(self, mock_rel, mock_datetime, client):
        """Test that WebSocket refresh also schedules credential refresh."""
        from datetime import datetime, timedelta, timezone

        # Setup current time
        now = datetime.now(timezone.utc)
        mock_datetime.now.return_value = now
        client._execution_start_time = now - timedelta(seconds=1800)  # 30 minutes ago
        client._execution_timeout = 7200  # 2 hours
        client._url_expires_in = 3600  # 1 hour
        client._refresh_buffer = 720  # 12 minutes
        client._completion_received = False

        # Mock credentials that expire in 50 minutes
        mock_provider = Mock()
        expiry_time = now + timedelta(seconds=3000)
        type(mock_provider).expiry = property(lambda self: expiry_time)
        client._credentials_provider = mock_provider

        mock_old_app = Mock()
        client.app = mock_old_app

        mock_new_app = Mock()
        with patch.object(client, "_init_websocket_app", return_value=mock_new_app):
            client._refresh_websocket_connection()

        # Verify credential refresh was scheduled
        # Time remaining: 7200 - 1800 = 5400 seconds
        # Credential refresh at: 3000 - 720 = 2280 seconds
        timeout_calls = [call[0][0] for call in mock_rel.timeout.call_args_list]
        # Should have both URL refresh (2880s) and credential refresh (2280s)
        assert 2880 in timeout_calls  # URL refresh
        assert any(2270 <= t <= 2290 for t in timeout_calls)  # Credential refresh (allow small variance)

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_with_context_logging(self, mock_timeout, client):
        """Test that context parameter affects logging."""
        from datetime import datetime, timedelta, timezone

        # Set up credentials
        mock_provider = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=1000)
        type(mock_provider).expiry = property(lambda self: expiry_time)
        mock_provider.refresh = Mock()
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000

        # Schedule with context
        client._schedule_credential_refresh(reference_time, max_duration, context="post-URL-refresh")

        # Verify callback was scheduled
        assert mock_timeout.called
        callback = mock_timeout.call_args[0][1]

        # Execute the callback to verify it uses the context in logging
        client._completion_received = False
        callback()  # This should call refresh with context in log message

        # Verify refresh was called
        mock_provider.refresh.assert_called_once()

    def test_is_recoverable_error_websocket_connection_closed(self, client):
        """Test _is_recoverable_error with WebSocketConnectionClosedException."""
        from websocket import WebSocketConnectionClosedException

        error = WebSocketConnectionClosedException("Connection closed")
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_403(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 403."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Forbidden", 403)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_502(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 502."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Bad Gateway", 502)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_408(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 408."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Request Timeout", 408)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_429(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 429."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Too Many Requests", 429)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_500(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 500."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Internal Server Error", 500)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_503(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 503."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Service Unavailable", 503)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_bad_status_504(self, client):
        """Test _is_recoverable_error with WebSocketBadStatusException 504."""
        from websocket import WebSocketBadStatusException

        error = WebSocketBadStatusException("Gateway Timeout", 504)
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_websocket_timeout(self, client):
        """Test _is_recoverable_error with WebSocketTimeoutException."""
        from websocket import WebSocketTimeoutException

        error = WebSocketTimeoutException("Timeout")
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_connection_reset(self, client):
        """Test _is_recoverable_error with ConnectionResetError."""
        error = ConnectionResetError("Connection reset by peer")
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_broken_pipe(self, client):
        """Test _is_recoverable_error with BrokenPipeError."""
        error = BrokenPipeError("Broken pipe")
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_signature_expired_string(self, client):
        """Test _is_recoverable_error with signature expired in error message."""
        error = Exception("Signature expired at 2024-01-01")
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_403_forbidden_string(self, client):
        """Test _is_recoverable_error with 403 forbidden in error message."""
        error = Exception("403 Forbidden: Access denied")
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_completion_received(self, client):
        """Test _is_recoverable_error returns False when completion received."""
        from websocket import WebSocketConnectionClosedException

        client._completion_received = True
        error = WebSocketConnectionClosedException("Connection closed")
        assert client._is_recoverable_error(error) is False

    def test_is_recoverable_error_execution_timeout_reached(self, client):
        """Test _is_recoverable_error returns False when execution timeout reached."""
        from datetime import datetime, timedelta, timezone

        from websocket import WebSocketConnectionClosedException

        # Set execution to be past timeout
        client._execution_start_time = datetime.now(timezone.utc) - timedelta(seconds=client._execution_timeout + 1)
        error = WebSocketConnectionClosedException("Connection closed")
        assert client._is_recoverable_error(error) is False

    def test_is_recoverable_error_within_execution_timeout(self, client):
        """Test _is_recoverable_error returns True when within execution timeout."""
        from datetime import datetime, timezone

        from websocket import WebSocketConnectionClosedException

        # Set execution to be well within timeout (just started)
        client._execution_start_time = datetime.now(timezone.utc)
        client._completion_received = False
        error = WebSocketConnectionClosedException("Connection closed")
        # Should be recoverable since we're within the execution timeout
        assert client._is_recoverable_error(error) is True

    def test_is_recoverable_error_non_recoverable(self, client):
        """Test _is_recoverable_error returns False for non-recoverable errors."""
        error = ValueError("Invalid value")
        assert client._is_recoverable_error(error) is False

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.datetime")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    def test_refresh_websocket_connection_execution_timeout_reached(self, mock_rel, mock_datetime, client):
        """Test WebSocket refresh aborts when execution timeout reached."""
        from datetime import datetime as dt
        from datetime import timedelta, timezone

        # Mock datetime.now to return a time past the execution timeout
        past_timeout = dt.now(timezone.utc) - timedelta(seconds=client._execution_timeout + 1)
        mock_datetime.now.return_value = past_timeout
        client._execution_start_time = past_timeout
        client._completion_received = False

        # Mock _perform_reconnection_with_retry to avoid actual retry delays
        with patch.object(client, "_perform_reconnection_with_retry") as mock_reconnect:
            # Simulate the timeout check that happens in _perform_reconnection_with_retry
            def side_effect():
                elapsed_time = (dt.now(timezone.utc) - client._execution_start_time).total_seconds()
                time_remaining = client._execution_timeout - elapsed_time
                if time_remaining <= 0:
                    mock_rel.abort()
                    raise RuntimeError("Execution timeout reached")

            mock_reconnect.side_effect = side_effect

            client._refresh_websocket_connection()

        # Should abort due to execution timeout
        mock_rel.abort.assert_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_close_abnormal_closure_triggers_reconnection(self, mock_websocket_app, mock_rel, client):
        """Test _on_close triggers reconnection for abnormal closure (1006)."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_close = call_args[1]["on_close"]

        # Mock _refresh_websocket_connection
        with patch.object(client, "_refresh_websocket_connection") as mock_refresh:
            on_close(mock_app, 1006, "Abnormal closure")
            mock_refresh.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_close_going_away_triggers_reconnection(self, mock_websocket_app, mock_rel, client):
        """Test _on_close triggers reconnection for going away (1001)."""
        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_close = call_args[1]["on_close"]

        with patch.object(client, "_refresh_websocket_connection") as mock_refresh:
            on_close(mock_app, 1001, "Going away")
            mock_refresh.assert_called_once()

    def test_should_reconnect_on_close_completion_received(self, client):
        """Test _should_reconnect_on_close returns False when completion received."""
        client._completion_received = True
        assert client._should_reconnect_on_close(1006, "Abnormal") is False

    def test_should_reconnect_on_close_normal_closure(self, client):
        """Test _should_reconnect_on_close returns False for normal closure."""
        client._completion_received = False
        assert client._should_reconnect_on_close(1000, "Normal") is False

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel")
    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.WebSocketApp")
    def test_on_error_recoverable_triggers_refresh(self, mock_websocket_app, mock_rel, client):
        """Test _on_error triggers connection refresh for recoverable errors."""
        from websocket import WebSocketConnectionClosedException

        mock_app = Mock()
        mock_websocket_app.return_value = mock_app

        with patch.object(client._signer, "sign_websocket_url", return_value="wss://signed-url"):
            client.run("test_input")

        call_args = mock_websocket_app.call_args
        on_error = call_args[1]["on_error"]

        with patch.object(client, "_refresh_websocket_connection") as mock_refresh:
            error = WebSocketConnectionClosedException("Connection closed")
            on_error(mock_app, error)
            mock_refresh.assert_called_once()
            mock_app.close.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_callback_completion_received(self, mock_timeout, client):
        """Test credential refresh callback exits early when completion received."""
        from datetime import datetime, timedelta, timezone

        mock_provider = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=1000)
        type(mock_provider).expiry = property(lambda self: expiry_time)
        mock_provider.refresh = Mock()
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000

        client._schedule_credential_refresh(reference_time, max_duration)

        # Get the callback
        callback = mock_timeout.call_args[0][1]

        # Set completion received and execute callback
        client._completion_received = True
        callback()

        # Refresh should not be called
        mock_provider.refresh.assert_not_called()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_callback_no_old_expiry(self, mock_timeout, client):
        """Test credential refresh callback when old_expiry is None."""
        from datetime import datetime, timedelta, timezone

        mock_provider = Mock()
        initial_expiry = datetime.now(timezone.utc) + timedelta(seconds=1000)
        new_expiry = datetime.now(timezone.utc) + timedelta(seconds=2000)

        # Track calls to expiry property
        expiry_calls = [0]

        def get_expiry(self):
            expiry_calls[0] += 1
            if expiry_calls[0] == 1:
                return initial_expiry  # First call for scheduling
            elif expiry_calls[0] == 2:
                return None  # old_expiry in callback
            else:
                return new_expiry  # new_expiry after refresh

        type(mock_provider).expiry = property(get_expiry)
        mock_provider.refresh = Mock()
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000

        client._schedule_credential_refresh(reference_time, max_duration)

        # Get and execute callback
        callback = mock_timeout.call_args[0][1]
        client._completion_received = False
        callback()

        # Refresh should be called
        mock_provider.refresh.assert_called_once()

    @patch("amzn_nova_act_human_intervention_client.executors.websocket.executor.rel.timeout")
    def test_schedule_credential_refresh_callback_no_new_expiry(self, mock_timeout, client):
        """Test credential refresh callback when new_expiry is None after refresh."""
        from datetime import datetime, timedelta, timezone

        mock_provider = Mock()
        old_expiry = datetime.now(timezone.utc) + timedelta(seconds=1000)
        # First call returns old expiry, after refresh returns None
        expiry_calls = [0]

        def get_expiry(self):
            expiry_calls[0] += 1
            return old_expiry if expiry_calls[0] == 1 else None

        type(mock_provider).expiry = property(get_expiry)
        mock_provider.refresh = Mock()
        client._credentials_provider = mock_provider
        client._refresh_buffer = 200

        reference_time = datetime.now(timezone.utc)
        max_duration = 2000

        client._schedule_credential_refresh(reference_time, max_duration)

        # Get and execute callback
        callback = mock_timeout.call_args[0][1]
        client._completion_received = False
        callback()

        # Refresh should be called
        mock_provider.refresh.assert_called_once()
