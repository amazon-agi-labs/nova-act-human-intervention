"""Constants for the Nova Act Human Intervention Client.

This module defines configuration constants for WebSocket connections, credential management,
and S3 storage used by intervention executors.

Examples
--------
Using timeout constants in executor configuration:

>>> from amzn_nova_act_human_intervention_client import ApprovalInterventionExecutor
>>> from amzn_nova_act_human_intervention_client.utils import constants
>>>
>>> # Use default timeout (1 hour)
>>> executor = ApprovalInterventionExecutor(
...     endpoint="wss://example.com",
...     intervention_context=context,
...     screenshot_s3_bucket="bucket",
...     credentials_provider=creds,
...     execution_timeout=constants.DEFAULT_EXECUTION_TIMEOUT
... )
>>>
>>> # Use maximum timeout (24 hours)
>>> long_executor = ApprovalInterventionExecutor(
...     endpoint="wss://example.com",
...     intervention_context=context,
...     screenshot_s3_bucket="bucket",
...     credentials_provider=creds,
...     execution_timeout=constants.MAX_EXECUTION_TIMEOUT
... )

Understanding credential refresh timing:

>>> from amzn_nova_act_human_intervention_client.utils import constants
>>>
>>> # Credentials expire in 3600 seconds (1 hour)
>>> url_expires_in = constants.MAX_URL_EXPIRES_IN  # 3600 seconds
>>> buffer_ratio = constants.CREDENTIAL_REFRESH_BUFFER_RATIO  # 0.2 (20%)
>>>
>>> # Refresh will occur at: 3600 * (1 - 0.2) = 2880 seconds (48 minutes)
>>> refresh_time = url_expires_in * (1 - buffer_ratio)
>>> print(f"Credentials will refresh after {refresh_time} seconds")
Credentials will refresh after 2880.0 seconds
"""

from typing import Final, Set

# Time constants (in seconds)
DEFAULT_EXECUTION_TIMEOUT: Final[int] = 3600
"""Default execution timeout in seconds (1 hour).

This is the default maximum duration for a human intervention workflow.
Used when no execution_timeout is specified when creating an executor.
"""

MAX_EXECUTION_TIMEOUT: Final[int] = 24 * 60 * 60
"""Maximum execution timeout in seconds (24 hours).

The longest duration allowed for a human intervention workflow.
Execution timeouts exceeding this value will be capped at this maximum.
"""

MIN_URL_EXPIRES_IN: Final[int] = 900
"""Minimum URL expiration time in seconds (15 minutes).

Due to IAM role-chaining limits, signed URLs cannot be shorter than 15 minutes.
This ensures sufficient time for the initial connection and authentication.
"""

MAX_URL_EXPIRES_IN: Final[int] = 3600
"""Maximum URL expiration time in seconds (1 hour).

Due to IAM role-chaining limits (STS:AssumeRole), signed URLs are capped at 1 hour.
For longer executions, the executor automatically refreshes the URL before expiration.
"""

CREDENTIAL_REFRESH_BUFFER_RATIO: Final[float] = 0.2
"""Credential refresh buffer as a ratio of URL expiration time (20%).

Credentials are refreshed at (1 - BUFFER_RATIO) * expiration_time to ensure
they don't expire during use. For example, with a 1-hour expiration:
    Refresh time = 3600 * (1 - 0.2) = 2880 seconds (48 minutes)
"""

WEBSOCKET_RECONNECT_INTERVAL: Final[int] = 0
"""WebSocket reconnection interval in seconds.

Set to 0 to disable automatic reconnection by the websocket-client library.
Reconnection is handled manually via _refresh_websocket_connection() to ensure
fresh signed URLs are used, preventing signature expiration errors.
"""

MAX_RECONNECTION_ATTEMPTS: Final[int] = 999999
"""Maximum number of reconnection attempts for unexpected connection drops.

Set very high to allow retries throughout the entire execution timeout period.
For long-running workflows (8-24 hours), the executor will keep retrying with
exponential backoff (1s, 2s, 4s, ..., up to 30s) plus random jitter until either:
- The workflow completes successfully, or
- The execution timeout is reached

This ensures resilience to transient server-side failures over many hours.
"""

RECOVERABLE_WEBSOCKET_CLOSE_CODES: Final[Set[int]] = {1001, 1006, 1012, 1013}
"""WebSocket close status codes that indicate recoverable errors.

These codes suggest temporary issues where reconnection may succeed:
- 1001 (Going Away): Server failure or navigating away
- 1006 (Abnormal Closure): No close frame received
- 1012 (Service Restart): Server restarting
- 1013 (Try Again Later): Server overloaded

See: https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent/code
"""

WEBSOCKET_PING_INTERVAL: Final[int] = 300
"""WebSocket ping interval in seconds (5 minutes).

Automatic ping frames are sent every 5 minutes to prevent API Gateway's
10-minute idle timeout. This keeps the connection alive during periods
of low message activity without interfering with application messages.
"""

WEBSOCKET_PING_TIMEOUT: Final[int] = 60
"""WebSocket ping timeout in seconds.

Maximum time to wait for a pong response after sending a ping.
Must be less than WEBSOCKET_PING_INTERVAL to detect connection issues.
If no pong is received within this time, the connection is considered dead.
"""

SIGINT_SIGNAL_NUMBER: Final[int] = 2
"""SIGINT signal number for graceful shutdown.

Used to handle Ctrl+C (SIGINT) for graceful termination of WebSocket connections.
The executor registers this signal to properly close connections and clean up resources.
"""

# S3 screenshot storage constants
S3_SCREENSHOT_OBJECT_KEY_TEMPLATE: Final[str] = "screenshot-{event_id}-{timestamp}{extension}"
"""S3 object key template for storing screenshots.

Template fields:
    - event_id: Unique identifier for the intervention event
    - timestamp: Current UTC timestamp in YYYYMMDD-HHMMSS format
    - extension: File extension (.txt for data URL text files)

Example output: "screenshot-abc123-20250109-143000.txt"
"""

S3_PRESIGNED_URL_EXPIRATION: Final[int] = 3600
"""Default S3 presigned URL expiration in seconds (1 hour).

Maximum duration that presigned URLs for screenshot access remain valid.
Capped by the execution timeout to ensure URLs don't outlive the workflow.
"""
