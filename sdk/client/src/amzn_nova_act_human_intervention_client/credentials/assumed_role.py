"""Assumed role credentials provider using AWS STS."""

import os
from datetime import datetime, timezone

import boto3  # type: ignore[import-untyped]
from amzn_nova_act_human_intervention_common import LoggingConfig
from botocore.credentials import Credentials  # type: ignore[import-untyped]

from amzn_nova_act_human_intervention_client.credentials.base import CredentialsProvider

logger = LoggingConfig.get_logger(__name__)

# Maximum duration for AssumeRole with role chaining (1 hour)
MAX_ASSUME_ROLE_DURATION = 3600
MIN_ASSUME_ROLE_DURATION = 900


class AssumedRoleCredentialsProvider(CredentialsProvider):
    """Credentials provider that assumes an IAM role via STS.

    This provider uses AWS STS AssumeRole to obtain temporary credentials.
    Credentials are refreshed by calling assume_role again.

    Note: When role chaining (assuming a role from an assumed role), the maximum
    duration is limited to 1 hour (3600 seconds) by AWS.

    Examples
    --------
    Basic usage with default session:

    >>> import boto3
    >>> from amzn_nova_act_human_intervention_client import AssumedRoleCredentialsProvider
    >>>
    >>> # Create provider that assumes a role for 1 hour
    >>> session = boto3.Session()
    >>> provider = AssumedRoleCredentialsProvider(
    ...     role_arn="arn:aws:iam::123456789012:role/MyRole",
    ...     duration_seconds=3600,
    ...     session=session
    ... )
    >>>
    >>> # Access credentials (automatically refreshed when needed)
    >>> creds = provider.credentials
    >>> print(f"Access Key: {creds.access_key}")
    >>> print(f"Expires at: {provider.expiry}")

    Using with a custom boto3 session (specific profile or region):

    >>> import boto3
    >>> from amzn_nova_act_human_intervention_client import AssumedRoleCredentialsProvider
    >>>
    >>> # Use specific profile or region - STS client will use this region
    >>> session = boto3.Session(profile_name="my-profile", region_name="us-east-1")
    >>> provider = AssumedRoleCredentialsProvider(
    ...     role_arn="arn:aws:iam::123456789012:role/MyRole",
    ...     duration_seconds=3600,
    ...     session=session,
    ...     role_session_name="my-custom-session"
    ... )

    Manual credential refresh:

    >>> import boto3
    >>> from amzn_nova_act_human_intervention_client import AssumedRoleCredentialsProvider
    >>>
    >>> session = boto3.Session()
    >>> provider = AssumedRoleCredentialsProvider(
    ...     role_arn="arn:aws:iam::123456789012:role/MyRole",
    ...     duration_seconds=3600,
    ...     session=session
    ... )
    >>>
    >>> # Manually refresh credentials before they expire
    >>> provider.refresh()
    >>> new_creds = provider.credentials
    """

    def __init__(
        self,
        role_arn: str,
        duration_seconds: int,
        session: boto3.Session,
        role_session_name: str = "websocket-client-session",
    ) -> None:
        """Initialize the assumed role credentials provider.

        Args:
            role_arn: ARN of the IAM role to assume
            duration_seconds: Duration for which credentials should be valid (900-3600 seconds).
                             Capped at 3600 seconds (1 hour) due to role chaining limits.
            session: boto3 Session to use for STS calls (region will be inherited from the session)
            role_session_name: Name for the role session (appears in CloudTrail logs)

        Raises:
            ValueError: If role_arn is empty or duration_seconds is invalid
        """
        if not role_arn:
            raise ValueError("role_arn is required")
        if not 900 <= duration_seconds <= 43200:
            raise ValueError("duration_seconds must be between 900 and 43200")

        self.role_arn = role_arn
        # Cap at MAX_ASSUME_ROLE_DURATION for role chaining
        self.duration_seconds = max(MIN_ASSUME_ROLE_DURATION, min(duration_seconds, MAX_ASSUME_ROLE_DURATION))
        self.role_session_name = role_session_name
        self._session = session
        self._credentials: Credentials | None = None
        self._expiry: datetime | None = None

        # Initial credential fetch
        self.refresh()

    @property
    def credentials(self) -> Credentials:
        """Get current AWS credentials.

        Returns:
            Credentials object with access key, secret key, and session token

        Raises:
            RuntimeError: If no credentials are available
        """
        if self._credentials is None:
            raise RuntimeError("No credentials available - refresh() may have failed")
        return self._credentials

    @property
    def expiry(self) -> datetime | None:
        """Get expiration time of current credentials.

        Returns:
            datetime: Expiration time in UTC, or None if not set
        """
        return self._expiry

    @staticmethod
    def _is_running_on_aws() -> bool:
        """Detect if running on AWS infrastructure.

        Checks for common AWS environment indicators:
        - ECS task metadata endpoint
        - EC2 instance metadata service
        - Lambda execution environment
        - EKS pod identity

        Returns:
            bool: True if running on AWS, False otherwise
        """
        # Check for Lambda environment
        if os.environ.get("AWS_EXECUTION_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            return True

        # Check for ECS environment
        if os.environ.get("ECS_CONTAINER_METADATA_URI") or os.environ.get("ECS_CONTAINER_METADATA_URI_V4"):
            return True

        # Check for EC2/EKS by attempting to reach instance metadata service (non-blocking check)
        # We check for the environment variable that's set on EC2/EKS instances
        if os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
            return True

        return False

    def refresh(self) -> None:
        """Refresh credentials by assuming the IAM role.

        Makes a new STS AssumeRole call to get fresh temporary credentials.

        Behavior differs based on environment:
        - On AWS (ECS/EKS/Lambda/EC2): Uses existing session (boto3 auto-refreshes role credentials)
        - Locally: Creates fresh session to pick up updated credentials from credential providers
          (e.g., credential_process, SSO, or any boto3 credential provider)

        Raises:
            RuntimeError: If STS AssumeRole fails
        """
        is_on_aws = self._is_running_on_aws()
        old_expiry = self._expiry

        # Log refresh start with current state
        if old_expiry:
            time_until_expiry = (old_expiry - datetime.now(timezone.utc)).total_seconds()
            logger.info(
                f"Starting credential refresh - current expiry: {old_expiry.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                f"time remaining: {int(time_until_expiry)}s, environment: {'AWS' if is_on_aws else 'local'}"
            )
        else:
            env = "AWS" if is_on_aws else "local"
            logger.info(
                f"Starting initial credential acquisition via AssumeRole - "
                f"role: {self.role_arn}, duration: {self.duration_seconds}s, environment: {env}"
            )

        try:
            # On AWS: boto3 automatically refreshes role credentials from metadata service
            # Locally: Create fresh session to trigger credential provider refresh
            #          (works with credential_process, SSO, and other providers)
            if is_on_aws:
                sts_client = self._session.client("sts")
            else:
                logger.debug("Creating fresh boto3 session to trigger credential provider refresh")
                fresh_session = boto3.Session(
                    region_name=self._session.region_name,
                    profile_name=self._session.profile_name,
                )
                sts_client = fresh_session.client("sts")

            logger.debug(f"Calling STS AssumeRole for {self.role_arn}")
            response = sts_client.assume_role(
                RoleArn=self.role_arn,
                RoleSessionName=self.role_session_name,
                DurationSeconds=self.duration_seconds,
            )

            creds = response["Credentials"]
            self._credentials = Credentials(
                access_key=creds["AccessKeyId"],
                secret_key=creds["SecretAccessKey"],
                token=creds["SessionToken"],
            )
            # Convert AWS STS expiration time to standard UTC timezone
            self._expiry = creds["Expiration"].astimezone(timezone.utc)

            # Log successful refresh with new expiry
            if old_expiry and self._expiry:
                time_extended = (self._expiry - old_expiry).total_seconds()
                logger.info(
                    f"Credential refresh completed successfully - "
                    f"new expiry: {self._expiry.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                    f"extended by: {int(time_extended)}s"
                )
            elif self._expiry:  # Initial acquisition - self._expiry should always be set at this point
                time_until_new_expiry = (self._expiry - datetime.now(timezone.utc)).total_seconds()
                logger.info(
                    f"Initial credentials acquired successfully - "
                    f"expiry: {self._expiry.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                    f"valid for: {int(time_until_new_expiry)}s"
                )

        except Exception as e:
            logger.error(f"Failed to assume role {self.role_arn}: {str(e)}")
            raise RuntimeError(f"Failed to assume role {self.role_arn}: {str(e)}") from e
