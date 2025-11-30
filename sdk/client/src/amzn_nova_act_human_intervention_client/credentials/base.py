"""Base credentials provider interface."""

from abc import ABC, abstractmethod
from datetime import datetime

from botocore.credentials import Credentials  # type: ignore[import-untyped]


class CredentialsProvider(ABC):
    """Abstract base class for AWS credentials providers.

    Implementations must provide properties to retrieve credentials and expiry,
    and a method to refresh credentials. The executor will handle scheduling
    of credential refresh based on expiry times.

    Examples
    --------
    Implementing a custom credentials provider:

    >>> from datetime import datetime, timezone, timedelta
    >>> from botocore.credentials import Credentials
    >>> from amzn_nova_act_human_intervention_client import CredentialsProvider
    >>>
    >>> class MyCredentialsProvider(CredentialsProvider):
    ...     def __init__(self):
    ...         self._creds = Credentials("ACCESS_KEY", "SECRET_KEY", "TOKEN")
    ...         self._expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    ...
    ...     @property
    ...     def credentials(self) -> Credentials:
    ...         return self._creds
    ...
    ...     @property
    ...     def expiry(self) -> datetime | None:
    ...         return self._expiry
    ...
    ...     def refresh(self) -> None:
    ...         # Implement refresh logic here
    ...         self._expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    """

    @property
    @abstractmethod
    def credentials(self) -> Credentials:
        """Get current AWS credentials.

        Returns:
            Credentials object containing access key, secret key, and optional session token

        Raises:
            RuntimeError: If credentials cannot be retrieved
        """

    @property
    @abstractmethod
    def expiry(self) -> datetime | None:
        """Get expiration time of current credentials.

        Returns:
            datetime: Expiration time in UTC, or None if credentials don't expire
        """

    @abstractmethod
    def refresh(self) -> None:
        """Refresh the credentials.

        Should update the credentials and expiry time.
        Called by the executor when credentials are about to expire.

        Raises:
            RuntimeError: If credentials cannot be refreshed
        """
