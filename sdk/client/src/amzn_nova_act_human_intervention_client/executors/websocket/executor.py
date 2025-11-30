"""WebSocket-based intervention executor with credential management."""

import json
import platform
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from amzn_nova_act_human_intervention_common import (
    AWSSigV4Signer,
    GenericDict,
    InterventionContext,
)
from rel import rel  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random
from websocket import (
    WebSocket,
    WebSocketApp,
    WebSocketBadStatusException,
    WebSocketConnectionClosedException,
    WebSocketTimeoutException,
)
from websocket import enableTrace as enableWebSocketAppTracing

from amzn_nova_act_human_intervention_client.credentials import CredentialsProvider
from amzn_nova_act_human_intervention_client.exceptions import WorkflowExecutionError
from amzn_nova_act_human_intervention_client.executors.base import BaseInterventionExecutor, T
from amzn_nova_act_human_intervention_client.utils.constants import (
    CREDENTIAL_REFRESH_BUFFER_RATIO,
    DEFAULT_EXECUTION_TIMEOUT,
    MAX_EXECUTION_TIMEOUT,
    MAX_RECONNECTION_ATTEMPTS,
    MAX_URL_EXPIRES_IN,
    MIN_URL_EXPIRES_IN,
    RECOVERABLE_WEBSOCKET_CLOSE_CODES,
    SIGINT_SIGNAL_NUMBER,
    WEBSOCKET_PING_INTERVAL,
    WEBSOCKET_PING_TIMEOUT,
    WEBSOCKET_RECONNECT_INTERVAL,
)


class WebsocketBasedInterventionExecutor(BaseInterventionExecutor[T]):
    """WebSocket-based intervention executor with credential management.

    Base class for executing human intervention processes via WebSocket connections.
    Handles connection management, message routing, completion handling, and credential
    management. Closes connection when URL expires.

    Uses the 'rel' event loop dispatcher to manage WebSocket connections asynchronously.
    The rel library provides signal handling and graceful shutdown capabilities,
    allowing the WebSocket connection to run indefinitely until completion or error.

    Keep-Alive Mechanism:
        Uses WebSocketApp's built-in ping/pong mechanism to prevent API Gateway's
        10-minute idle timeout. The executor configures automatic ping frames to be
        sent every 5 minutes (WEBSOCKET_PING_INTERVAL) via the run_forever() method.
        This maintains the connection during periods of low message activity, ensuring
        that connectionIds stored in DynamoDB remain valid throughout long-running
        workflows, even when no application messages are being exchanged between
        client and server.

        The built-in ping mechanism:
        - Runs in a separate daemon thread managed by WebSocketApp
        - Automatically starts when the connection opens
        - Stops when the connection closes
        - Does not interfere with application-level messaging

    Type Parameters
    ---------------
    T : TypeVar
        The type of input data for the intervention (e.g., ApprovalRequest, UITakeoverRequest)

    Notes
    -----
    Subclasses must implement:
        - _on_message(): Handle incoming WebSocket messages
        - _create_message(): Create intervention-specific messages

    The executor automatically handles:
        - Credential refresh based on expiry times
        - WebSocket URL refresh for long-running executions
        - Connection keep-alive via ping/pong
        - Graceful shutdown on completion or error
    """

    def __init__(
        self,
        endpoint: str,
        intervention_context: InterventionContext,
        credentials_provider: CredentialsProvider,
        region: str = "us-west-2",
        execution_timeout: int = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        """Initialize the WebSocket intervention executor.

        Args:
            endpoint: WebSocket endpoint URL
            intervention_context: Context information for the intervention
            credentials_provider: Provider for AWS credentials (handles refresh)
            region: AWS region for SigV4 signing
            execution_timeout: URL expiration time in seconds (default: 1 hour, max: 24 hours)
        """
        self._validate_websocket_url(endpoint)
        super().__init__(endpoint, intervention_context)

        # WebSocket and connection management
        self.app: WebSocketApp | None = None
        self._is_reconnecting = False
        self._is_url_refresh = False  # Track if reconnection is due to URL refresh
        self._reconnection_count = 0  # Track number of reconnection attempts
        self._input_data: T | None = None
        self._event_id: str | None = None  # Store event ID for connection refresh
        self._completion_received = False
        self._exception: Exception | None = None

        # AWS and signing configuration
        self.region = region
        self._credentials_provider = credentials_provider
        self._signer = AWSSigV4Signer(region=region, service="execute-api")
        self._execution_action_name = "start-hitl-flow"

        # Timeouts
        self._execution_timeout = min(execution_timeout, MAX_EXECUTION_TIMEOUT)
        # Clamp invocation URL expiration between 15 minutes
        # (900s) and 1 hour (3600s) for IAM role-chaining (STS:AssumeRole) TTL limits.
        self._url_expires_in = max(MIN_URL_EXPIRES_IN, min(self._execution_timeout, MAX_URL_EXPIRES_IN))
        # Refresh invocation URL at 20% buffer.
        self._refresh_buffer = int(CREDENTIAL_REFRESH_BUFFER_RATIO * self._url_expires_in)

        # Credential management
        self._execution_start_time = datetime.now(timezone.utc)

    def _validate_websocket_url(self, endpoint: str) -> None:
        """Validate that the endpoint is a WebSocket URL.

        Args:
            endpoint: URL to validate

        Raises:
            ValueError: If the endpoint is not a valid WebSocket URL
        """
        if not endpoint.startswith(("ws://", "wss://")):
            raise ValueError(f"Invalid WebSocket URL: {endpoint}. Must start with 'ws://' or 'wss://'")

    def _ensure_valid_credentials(self) -> None:
        """Ensure credentials are valid and refresh if needed via provider."""
        credentials_expiry = self._credentials_provider.expiry
        if credentials_expiry and self._execution_start_time >= credentials_expiry:
            self.logger.info("Credentials expired, refreshing via provider...")
            self._credentials_provider.refresh()

    def _schedule_credential_refresh(self, reference_time: datetime, max_duration: float, context: str = "") -> None:
        """Schedule credential refresh before credentials expire.

        Args:
            reference_time: Time to calculate expiry from (execution start or current time)
            max_duration: Maximum duration to schedule within (in seconds)
            context: Optional context string for logging (e.g., "initial" or "post-URL-refresh")
        """
        credentials_expiry = self._credentials_provider.expiry
        if credentials_expiry:
            time_until_cred_expiry = (credentials_expiry - reference_time).total_seconds()
            time_until_cred_refresh = time_until_cred_expiry - self._refresh_buffer

            # Log current credential expiry information
            context_str = f" ({context})" if context else ""
            self.logger.info(
                f"Credential expiry check{context_str}: "
                f"expires at {credentials_expiry.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                f"time until expiry: {int(time_until_cred_expiry)}s, "
                f"time until refresh: {int(time_until_cred_refresh)}s"
            )

            # Only schedule refresh if it would happen before max_duration and is in the future
            if 0 < time_until_cred_refresh < max_duration:

                def refresh_credentials() -> None:
                    if not self._completion_received:
                        old_expiry = self._credentials_provider.expiry
                        log_msg = "Refreshing credentials before expiration"
                        if context:
                            log_msg += f" ({context})"
                        old_expiry_str = old_expiry.strftime("%Y-%m-%d %H:%M:%S %Z") if old_expiry else "N/A"
                        self.logger.info(f"{log_msg} - old expiry: {old_expiry_str}")

                        # Perform the refresh
                        self._credentials_provider.refresh()

                        # Log new expiry after refresh
                        new_expiry = self._credentials_provider.expiry
                        if new_expiry:
                            new_expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S %Z")
                            if old_expiry:
                                extended_by = int((new_expiry - old_expiry).total_seconds())
                                self.logger.info(
                                    f"Credential refresh completed - new expiry: {new_expiry_str}, "
                                    f"extended by {extended_by}s"
                                )
                            else:
                                self.logger.info(f"Credential refresh completed - new expiry: {new_expiry_str}")
                        else:
                            self.logger.warning("Credential refresh completed but no new expiry time available")

                rel.timeout(int(time_until_cred_refresh), refresh_credentials)
                self.logger.info(
                    f"Scheduled credential refresh in {int(time_until_cred_refresh)}s "
                    f"(at {(reference_time + timedelta(seconds=time_until_cred_refresh)).strftime('%H:%M:%S')})"
                )
            else:
                if time_until_cred_refresh <= 0:
                    self.logger.warning(
                        f"Credential refresh not scheduled{context_str} - would have occurred in the past "
                        f"(time_until_refresh: {int(time_until_cred_refresh)}s)"
                    )
                else:
                    self.logger.info(
                        f"Credential refresh not scheduled{context_str} - would occur after max_duration "
                        f"(time_until_refresh: {int(time_until_cred_refresh)}s, max_duration: {int(max_duration)}s)"
                    )
        else:
            context_str = f" ({context})" if context else ""
            self.logger.info(f"No credential expiry time available{context_str}, skipping refresh scheduling")

    def _schedule_expiry_checks(self) -> None:
        """Schedule credential refresh and URL expiry checks.

        Sets up two types of scheduled callbacks:
        1. URL expiry check - closes connection when signed URL expires
        2. Credential refresh - refreshes AWS credentials before they expire

        The credential refresh only occurs if:
        - Credentials have an expiry time
        - Refresh would happen before URL expires
        - Connection hasn't completed
        """

        # Schedule hard deadline at execution timeout (not URL expiry if execution is longer)
        def close_on_timeout() -> None:
            if not self._completion_received:
                self.logger.info("Execution timeout reached, closing connection")
                self._close_expired_connection()

        # rel.timeout: Schedule a callback to execute after specified seconds
        rel.timeout(self._execution_timeout, close_on_timeout)
        self.logger.info(f"Scheduled connection close in {self._execution_timeout} seconds at execution timeout")

        # Schedule WebSocket URL refresh if execution timeout exceeds URL expiration
        if self._execution_timeout > self._url_expires_in:
            time_until_url_refresh = self._url_expires_in - self._refresh_buffer

            def refresh_websocket_url() -> None:
                if not self._completion_received:
                    self.logger.info("Refreshing WebSocket URL before expiration")
                    self._refresh_websocket_connection()

            # Schedule URL refresh before it expires
            rel.timeout(int(time_until_url_refresh), refresh_websocket_url)
            self.logger.info(
                f"Scheduled WebSocket URL refresh in {int(time_until_url_refresh)} seconds "
                f"(execution continues for {self._execution_timeout}s total)"
            )

        # Schedule initial credential refresh
        self._schedule_credential_refresh(
            reference_time=self._execution_start_time, max_duration=self._url_expires_in, context="initial"
        )

    def _refresh_websocket_connection(self) -> None:
        """Refresh WebSocket connection with a new signed URL and reschedule refreshes.

        Uses tenacity for exponential backoff retry logic. This is called by
        error/close handlers for unexpected disconnections, and also for scheduled
        proactive URL refreshes.

        Performs the following operations:
        1. Closes the current WebSocket connection
        2. Reconnects with a fresh signed URL to extend execution beyond URL expiration
        3. Schedules the next WebSocket URL refresh if execution timeout hasn't been reached
        4. Schedules credential refresh for long-running workflows spanning multiple URL refreshes
        """
        try:
            self._perform_reconnection_with_retry()
        except Exception as e:
            elapsed_time = (datetime.now(timezone.utc) - self._execution_start_time).total_seconds()
            self.logger.error(
                f"Reconnection failed after {self._reconnection_count} attempts (elapsed: {int(elapsed_time)}s): {e}"
            )
            rel.abort()

    @retry(
        stop=stop_after_attempt(MAX_RECONNECTION_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=30) + wait_random(0, 1),
        reraise=True,
    )
    def _perform_reconnection_with_retry(self) -> None:
        """Perform reconnection attempt with exponential backoff retry.

        This method is wrapped with tenacity's retry decorator to automatically
        retry with exponential backoff (1s, 2s, 4s, ..., up to 30s) plus random jitter.

        Raises:
            Exception: If reconnection fails, allowing tenacity to retry
        """
        if self._completion_received:
            return

        self._reconnection_count += 1
        elapsed_time = (datetime.now(timezone.utc) - self._execution_start_time).total_seconds()
        time_remaining = self._execution_timeout - elapsed_time
        self.logger.info(
            f"Attempting WebSocket reconnection (attempt #{self._reconnection_count}, "
            f"elapsed: {int(elapsed_time)}s, remaining: {int(time_remaining)}s)"
        )

        # Close current connection
        if self.app:
            self.logger.info(f"Closing old WebSocket connection - old_app_id: {id(self.app)}")
            self.app.close()

        # Calculate time remaining in execution
        elapsed_time = (datetime.now(timezone.utc) - self._execution_start_time).total_seconds()
        time_remaining = self._execution_timeout - elapsed_time

        if time_remaining <= 0:
            self.logger.info("Execution timeout reached during refresh, closing")
            rel.abort()
            raise RuntimeError("Execution timeout reached")

        # Mark this as a URL refresh reconnection
        self._is_url_refresh = True

        # Create new WebSocket app with fresh signed URL
        self.app = self._init_websocket_app()
        self.logger.info(f"Created new WebSocket app - new_app_id: {id(self.app)}")

        # Register new WebSocket app with the existing event loop
        self.app.run_forever(
            dispatcher=rel,
            reconnect=WEBSOCKET_RECONNECT_INTERVAL,
            ping_interval=WEBSOCKET_PING_INTERVAL,
            ping_timeout=WEBSOCKET_PING_TIMEOUT,
        )

        # Schedule next URL refresh if needed
        if time_remaining > self._url_expires_in:
            time_until_next_refresh = self._url_expires_in - self._refresh_buffer

            def refresh_again() -> None:
                if not self._completion_received:
                    self.logger.info("Refreshing WebSocket URL again before expiration")
                    self._refresh_websocket_connection()

            rel.timeout(int(time_until_next_refresh), refresh_again)
            self.logger.info(f"Scheduled next WebSocket URL refresh in {int(time_until_next_refresh)} seconds")

        # Schedule credential refresh for the newly refreshed credentials
        # This is critical for long-running workflows that span multiple URL refreshes
        self._schedule_credential_refresh(
            reference_time=datetime.now(timezone.utc), max_duration=time_remaining, context="post-URL-refresh"
        )

    def _close_expired_connection(self) -> None:
        """Close connection when execution timeout has been reached.

        Gracefully closes the WebSocket connection and stops the event loop
        when the execution timeout has been reached.
        """
        if self._completion_received:
            return

        self.logger.info("Closing connection due to execution timeout")
        if self.app:
            self.app.close()
        # rel.abort: Stop the rel event loop to terminate the connection permanently
        rel.abort()

    def _init_websocket_app(self) -> WebSocketApp:
        """Create a WebSocket app with fresh signed URL.

        Returns:
            Configured WebSocketApp instance

        Raises:
            RuntimeError: If no credentials are available
        """
        self._ensure_valid_credentials()

        credentials = self._credentials_provider.credentials

        expires_in = self._url_expires_in
        # Cap expires_in at MAX_URL_EXPIRES_IN due to IAM role-chaining limits
        if expires_in > MAX_URL_EXPIRES_IN:
            expires_in = MAX_URL_EXPIRES_IN

        signed_url = self._signer.sign_websocket_url(self._endpoint, credentials, expires_in=expires_in)

        enableWebSocketAppTracing(False)
        return WebSocketApp(
            url=signed_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_ping=self._on_ping,
            on_pong=self._on_pong,
        )

    def run(self, input_data: T) -> None:
        """Execute intervention with input data.

        Args:
            input_data: Intervention-specific input data

        Raises:
            WorkflowExecutionError: If the workflow fails with FAILED or TERMINATED status
        """
        self._input_data = input_data
        self._completion_received = False
        self._exception = None

        if platform.system() == "Darwin":
            # Initialize rel with poll/select on macOS to avoid kqueue reconnection issues
            # See: https://github.com/websocket-client/websocket-client/issues/977
            rel.initialize(["poll", "select"])

        self.app = self._init_websocket_app()
        self._schedule_expiry_checks()

        # Use rel as the event dispatcher for WebSocket connection management
        # Use built-in ping mechanism to prevent API Gateway idle timeout (10 minutes)
        self.app.run_forever(
            dispatcher=rel,
            reconnect=WEBSOCKET_RECONNECT_INTERVAL,
            ping_interval=WEBSOCKET_PING_INTERVAL,
            ping_timeout=WEBSOCKET_PING_TIMEOUT,
        )
        # rel.signal: Register signal handler for SIGINT (Ctrl+C) to gracefully abort
        rel.signal(SIGINT_SIGNAL_NUMBER, rel.abort)
        # rel.dispatch: Start the event loop and block until rel.abort() is called
        rel.dispatch()

        # Re-raise any exception that occurred during execution
        if self._exception:
            raise self._exception

    @abstractmethod
    def _on_message(self, app: WebSocket, message: str) -> None:
        """Handle incoming WebSocket messages.

        Subclasses must implement this method to handle use-case specific message types.
        Common pattern:
        - Parse JSON message
        - Handle "workflow_started" message type
        - Handle "workflow_completed" message type
        - Call _handle_completion() when workflow completes
        - Set self._completion_received = True on completion
        - Store exceptions for failed workflows in self._exception

        Args:
            app: WebSocket connection
            message: Raw message string received from server
        """

    def _on_error(self, app: WebSocket, error: Exception) -> None:
        """Handle WebSocket errors.

        Args:
            app: WebSocket connection
            error: Exception that occurred during WebSocket communication
        """
        self.logger.error(f"WebSocket error: {error}")

        # Check if this is a recoverable error (signature expiration, connection loss)
        if self._is_recoverable_error(error) and not self._completion_received:
            self.logger.info("Recoverable error detected, triggering connection refresh")
            app.close()
            self._refresh_websocket_connection()
            return

        # Store exception if it's from our workflow failure
        if isinstance(error, WorkflowExecutionError) and not self._exception:
            self._exception = error

        # For all other errors, close and abort
        app.close()
        # rel.abort: Stop the rel event loop, causing rel.dispatch() to return
        # This effectively terminates the WebSocket connection and any scheduled callbacks
        rel.abort()

    def _is_recoverable_error(self, error: Exception) -> bool:
        """Determine if an error is recoverable via connection refresh.

        Recoverable errors include:
        - WebSocket connection closed unexpectedly
        - Bad status codes (403 signature expired, 502/503/504 server errors)
        - Timeout exceptions
        - Network connection errors

        For long-running workflows (8-24 hours), the executor will keep retrying
        until either the workflow completes or the execution timeout is reached.

        Args:
            error: Exception that occurred during WebSocket communication

        Returns:
            True if the error is recoverable, False otherwise
        """
        # Stop retrying if workflow already completed
        if self._completion_received:
            return False

        # Check if execution timeout has been reached
        elapsed_time = (datetime.now(timezone.utc) - self._execution_start_time).total_seconds()
        if elapsed_time >= self._execution_timeout:
            self.logger.warning(
                f"Execution timeout reached ({elapsed_time:.0f}s >= {self._execution_timeout}s), not retrying"
            )
            return False

        # WebSocket-specific exceptions
        if isinstance(error, WebSocketConnectionClosedException):
            return True

        if isinstance(error, WebSocketBadStatusException):
            # Recoverable status codes (transient server-side errors):
            # - 403: Signature expired (authentication issue)
            # - 408: Request Timeout (temporary timeout)
            # - 429: Too Many Requests (rate limiting)
            # - 500: Internal Server Error (temporary server issue)
            # - 502: Bad Gateway (temporary proxy issue)
            # - 503: Service Unavailable (temporary server overload)
            # - 504: Gateway Timeout (temporary timeout)
            return error.status_code in {
                HTTPStatus.FORBIDDEN.value,
                HTTPStatus.REQUEST_TIMEOUT.value,
                HTTPStatus.TOO_MANY_REQUESTS.value,
                HTTPStatus.INTERNAL_SERVER_ERROR.value,
                HTTPStatus.BAD_GATEWAY.value,
                HTTPStatus.SERVICE_UNAVAILABLE.value,
                HTTPStatus.GATEWAY_TIMEOUT.value,
            }

        if isinstance(error, WebSocketTimeoutException):
            return True

        # Standard connection errors
        if isinstance(error, (ConnectionError, ConnectionResetError, BrokenPipeError)):
            return True

        # Fallback: Check error message for signature expiration
        # This handles cases where the error isn't wrapped in a specific exception type
        error_str = str(error).lower()
        if "signature expired" in error_str or ("403" in error_str and "forbidden" in error_str):
            return True

        return False

    def _on_close(self, app: WebSocket, close_status_code: int, close_msg: str) -> None:
        """Handle WebSocket connection close.

        Status code values:
        - Numeric value (e.g., 1000, 1001, 1012): Server closed connection with a close frame
        - None: Programmatic close (app.close()) or abnormal connection loss

        See: https://github.com/websocket-client/websocket-client/blob/master/websocket/_app.py
        The teardown() method calls _get_close_args(close_frame), which returns [None, None]
        when no close frame is received (programmatic or abnormal closes).

        Args:
            app: WebSocketApp instance that closed
            close_status_code: WebSocket close status code or None
            close_msg: Close message from server or None
        """
        self.logger.info(
            f"Connection closed - status: {close_status_code}, message: {close_msg}, "
            f"app_id: {id(app)}, current_app_id: {id(self.app)}"
        )

        # Ignore close events from stale WebSocketApp instances
        # This happens when we close an old connection during reconnection
        # and the close event fires after the new connection is established
        if app != self.app:
            self.logger.info(
                f"Ignoring close event from stale WebSocketApp instance "
                f"(stale_app_id: {id(app)}, current_app_id: {id(self.app)})"
            )
            return

        # Check if this is an unexpected close that should trigger reconnection
        if self._should_reconnect_on_close(close_status_code, close_msg):
            self.logger.info("Unexpected connection close, triggering connection refresh")
            self._refresh_websocket_connection()
            return

        # Normal close or completion
        app.close()
        # rel.abort: Stop the rel event loop since connection is permanently closed
        rel.abort()

    def _should_reconnect_on_close(self, status_code: int, message: str) -> bool:
        """Determine if a close should trigger reconnection.

        Returns True for recoverable WebSocket close codes (1001, 1006, 1012, 1013).
        See RECOVERABLE_WEBSOCKET_CLOSE_CODES constant for details.

        Args:
            status_code: WebSocket close status code
            message: Close message from the server

        Returns:
            True if reconnection should be attempted, False otherwise
        """
        if self._completion_received:
            return False

        return status_code in RECOVERABLE_WEBSOCKET_CLOSE_CODES

    def _on_open(self, app: WebSocket) -> None:
        """Handle WebSocket connection open."""
        self.logger.info(f"Opened connection - app_id: {id(app)}, current_app_id: {id(self.app)}")

        # Log successful reconnection if this was after failures
        if self._reconnection_count > 0:
            elapsed_time = (datetime.now(timezone.utc) - self._execution_start_time).total_seconds()
            self.logger.info(
                f"✓ Connection recovered after {self._reconnection_count} reconnection attempt(s) "
                f"(total elapsed: {int(elapsed_time)}s)"
            )

        # Reset reconnection counter on successful connection
        self._reconnection_count = 0

        # If this is a URL refresh reconnection, send connection-refresh message
        if self._is_url_refresh and self._event_id:
            self.logger.info(
                f"URL refresh reconnection - sending connection-refresh message for event {self._event_id}"
            )
            refresh_message = {
                "action": "connection-refresh",
                "eventId": self._event_id,
            }
            app.send(json.dumps(refresh_message))
            self._is_url_refresh = False
        # If this is initial connection, send the initial workflow message
        elif not self._is_reconnecting and self._input_data is not None:
            message = self._create_message(self._input_data)
            # Extract and store event_id for future connection refreshes
            if "input" in message and "event_id" in message["input"]:
                self._event_id = message["input"]["event_id"]
                self.logger.info(f"Stored event ID for connection tracking: {self._event_id}")
            app.send(json.dumps(message))

        # Normal reconnection (e.g., network interruption)
        elif self._is_reconnecting:
            self.logger.info("Reconnected successfully - connection restored")
            self._is_reconnecting = False

    def _on_ping(self, app: WebSocket, message: str) -> None:
        """Handle incoming WebSocket ping.

        Args:
            app: WebSocket application instance
            message: Ping message payload
        """
        self.logger.info("Sent heart beat to executor endpoint")

    def _on_pong(self, app: WebSocket, message: str) -> None:
        """Handle incoming WebSocket pong.

        Args:
            app: WebSocket application instance
            message: Pong message payload
        """
        self.logger.info("Received heart beat response from executor endpoint")

    @abstractmethod
    def _create_message(self, input_data: T) -> GenericDict:
        """Create WebSocket message from input data.

        Args:
            input_data: Workflow-specific input data

        Returns:
            Dictionary representation of the WebSocket message
        """

    def _handle_completion(self, ws: WebSocket, message: GenericDict) -> None:
        """Handle intervention completion.

        Args:
            ws: WebSocket connection
            message: Completion message received
        """
        self._completion_received = True
        ws.close()
        # rel.abort: Stop the rel event loop as the intervention has completed successfully
        rel.abort()
