"""SigV4 signing utilities for WebSocket connections to API Gateway."""

from botocore.auth import SigV4QueryAuth  # type: ignore[import-untyped]
from botocore.awsrequest import AWSRequest  # type: ignore[import-untyped]
from botocore.credentials import Credentials  # type: ignore[import-untyped]


class AWSSigV4Signer:
    """AWS SigV4 signature generator for WebSocket connections.

    This class provides utilities to sign AWS WebSocket URLs using SigV4 authentication,
    enabling secure connections to API Gateway WebSocket endpoints.
    """

    def __init__(self, region: str, service: str) -> None:
        """Initialize the SigV4 signer.

        Parameters
        ----------
        region : str
            AWS region (e.g., 'us-west-2')
        service : str
            AWS service name (e.g., 'execute-api')
        """
        self.region = region
        self.service = service

    def sign_websocket_url(self, websocket_url: str, credentials: Credentials, expires_in: int = 3600) -> str:
        """Sign a WebSocket URL with SigV4 authentication for API Gateway.

        Parameters
        ----------
        websocket_url : str
            WebSocket URL to sign (wss:// or ws://)
        credentials : Credentials
            AWS credentials containing access key, secret key, and optional session token
        expires_in : int, default=3600
            URL expiration time in seconds (max 3600 for assumed roles)

        Returns
        -------
        str
            Signed WebSocket URL with SigV4 query parameters

        Raises
        ------
        ValueError
            If the signed URL generation fails

        Notes
        -----
        WebSocket URL to HTTP Conversion:
            AWS SigV4 signing was designed for HTTP and doesn't natively support WebSocket
            protocols. This method converts ws://→http:// or wss://→https:// for signing,
            then converts back to the WebSocket scheme.

        The signed URL includes authentication query parameters (X-Amz-Algorithm,
        X-Amz-Credential, X-Amz-Date, X-Amz-Signature) that API Gateway validates
        during the WebSocket handshake.

        Examples
        --------
        Sign a WebSocket URL for API Gateway connection::

            >>> import boto3
            >>> from botocore.credentials import Credentials
            >>>
            >>> # Create SigV4 signer
            >>> signer = AWSSigV4Signer(region='us-east-1', service='execute-api')
            >>>
            >>> # Get credentials from boto3 session
            >>> session = boto3.Session()
            >>> credentials = session.get_credentials()
            >>>
            >>> # Sign the WebSocket URL
            >>> ws_url = "wss://abc123.execute-api.us-east-1.amazonaws.com/prod"
            >>> signed_url = signer.sign_websocket_url(ws_url, credentials, expires_in=3600)
            >>> print(signed_url)
            wss://abc123.execute-api.us-east-1.amazonaws.com/prod?X-Amz-Algorithm=...&X-Amz-Credential=...

        The signed URL can then be used to establish a WebSocket connection::

            >>> import websockets
            >>> async with websockets.connect(signed_url) as websocket:
            ...     await websocket.send("Hello, API Gateway!")
        """
        # Convert WebSocket URL to HTTP for signing
        http_url = websocket_url.replace("wss://", "https://").replace("ws://", "http://")

        # Create presigned request
        request = AWSRequest(method="GET", url=http_url)
        signer = SigV4QueryAuth(credentials, self.service, self.region, expires=expires_in)
        signer.add_auth(request)

        if request.url is None:
            raise ValueError("Signed URL is None")

        # Convert back to WebSocket scheme
        signed_url = request.url.replace("https://", "wss://").replace("http://", "ws://")
        return signed_url
