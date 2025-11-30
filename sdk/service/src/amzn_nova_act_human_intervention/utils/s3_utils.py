"""Utility class for handling S3 presigned URLs."""

from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import boto3
from amzn_nova_act_human_intervention_common import LoggingConfig

logger = LoggingConfig.get_logger(__name__)


class S3PresignedUrlHandler:
    """Handler for S3 presigned URL operations.

    Provides utilities to:
    - Generate presigned URLs for S3 objects with expiration
    - Parse presigned URLs to extract bucket and key
    - Download objects from S3 and convert to Base64 data URLs
    - Delete objects from S3
    """

    def __init__(self, s3_client: Optional[boto3.client] = None) -> None:
        """Initialize the S3 presigned URL handler.

        Args:
            s3_client: Optional boto3 S3 client. If not provided, creates a new client.
        """
        if s3_client is None:
            session = boto3.Session()
            self._s3_client = session.client("s3")
        else:
            self._s3_client = s3_client

    def generate_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for S3 object with expiration.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            expires_in: Number of seconds until the URL expires (default: 1 hour)

        Returns:
            Presigned URL that expires after the specified duration

        Example:
            >>> handler = S3PresignedUrlHandler()
            >>> url = handler.generate_presigned_url(
            ...     bucket="my-bucket",
            ...     key="screenshots/image.png",
            ...     expires_in=3600
            ... )
            >>> # Returns: "https://my-bucket.s3.amazonaws.com/screenshots/image.png?..."

        The presigned URL provides time-limited access to the S3 object without
        requiring the requester to have AWS credentials.
        """
        try:
            url = self._s3_client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
            )
            logger.info(f"Generated presigned URL for s3://{bucket}/{key} (expires in {expires_in}s)")
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for s3://{bucket}/{key}: {str(e)}")
            raise

    @staticmethod
    def parse_presigned_url(presigned_url: str) -> Optional[Tuple[str, str]]:
        """Parse S3 presigned URL to extract bucket and key.

        Args:
            presigned_url: Presigned S3 URL (e.g., https://bucket.s3.amazonaws.com/key?...)

        Returns:
            Tuple of (bucket, key) if successful, None otherwise

        Example:
            >>> url = "https://my-bucket.s3.us-east-1.amazonaws.com/screenshots/image.png?X-Amz-..."
            >>> result = S3PresignedUrlHandler.parse_presigned_url(url)
            >>> result
            ('my-bucket', 'screenshots/image.png')

        Supports both URL formats:
        - https://bucket.s3.amazonaws.com/key
        - https://bucket.s3.region.amazonaws.com/key
        """
        try:
            parsed = urlparse(presigned_url)

            # Handle both URL formats:
            # https://bucket.s3.amazonaws.com/key or https://s3.amazonaws.com/bucket/key
            if ".s3.amazonaws.com" in parsed.netloc or ".s3." in parsed.netloc:
                # Format: https://bucket.s3.region.amazonaws.com/key
                bucket = parsed.netloc.split(".")[0]
                key = unquote(parsed.path.lstrip("/"))

                if bucket and key:
                    return (bucket, key)

            logger.warning(f"Unable to parse S3 URL: {presigned_url}")
            return None

        except Exception as e:
            logger.error(f"Failed to parse presigned URL: {str(e)}")
            return None

    def convert_to_data_url(self, presigned_url: str) -> str:
        """Download data URL text from S3.

        The client uploads the complete data URL as a text file (e.g., "data:image/png;base64,...").
        This method simply downloads that text and returns it directly - no encoding/decoding needed.

        Args:
            presigned_url: Presigned S3 URL to the text file containing the data URL

        Returns:
            Complete data URL string (e.g., "data:image/png;base64,...")
            Falls back to original presigned URL if download fails

        Example:
            >>> handler = S3PresignedUrlHandler()
            >>> presigned_url = "https://my-bucket.s3.amazonaws.com/screenshot.txt?X-Amz-..."
            >>> data_url = handler.convert_to_data_url(presigned_url)
            >>> data_url
            'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...'

        This allows embedding the image directly in HTML, eliminating the need
        to keep the object in S3 after processing.
        """
        try:
            # Parse URL to extract bucket and key
            result = self.parse_presigned_url(presigned_url)
            if result is None:
                logger.error(f"Could not parse presigned URL: {presigned_url}")
                return presigned_url  # Fallback to original URL

            bucket, key = result

            # Download the text file from S3
            logger.info(f"Downloading data URL text from S3: s3://{bucket}/{key}")
            response = self._s3_client.get_object(Bucket=bucket, Key=key)
            data_url = response["Body"].read().decode("utf-8")

            logger.info(f"Downloaded data URL from S3 ({len(data_url)} characters)")
            return data_url

        except Exception as e:
            logger.error(f"Failed to download data URL from S3: {str(e)}")
            return presigned_url  # Fallback to original URL

    def delete_object(self, presigned_url: str) -> bool:
        """Delete object from S3.

        Args:
            presigned_url: Presigned S3 URL to the object

        Returns:
            True if deletion was successful, False otherwise

        The object is deleted after being processed (e.g., embedded in HTML).
        This cleanup happens immediately after use (typically within 2 minutes of upload).
        """
        try:
            # Parse URL to extract bucket and key
            result = self.parse_presigned_url(presigned_url)
            if result is None:
                logger.warning(f"Could not parse presigned URL: {presigned_url}")
                return False

            bucket, key = result

            logger.info(f"Deleting object from S3: s3://{bucket}/{key}")
            self._s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Successfully deleted object: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete object from S3: {str(e)}")
            return False
