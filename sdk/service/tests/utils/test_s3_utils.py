"""Tests for S3 utilities module."""

from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from amzn_nova_act_human_intervention.utils.s3_utils import S3PresignedUrlHandler


class TestS3PresignedUrlHandler:
    """Test cases for S3PresignedUrlHandler class."""

    @patch("amzn_nova_act_human_intervention.utils.s3_utils.boto3")
    def test_init_without_client(self, mock_boto3: Mock) -> None:
        """Test initialization without providing S3 client."""
        mock_session = Mock()
        mock_s3_client = Mock()
        mock_boto3.Session.return_value = mock_session
        mock_session.client.return_value = mock_s3_client

        handler = S3PresignedUrlHandler()

        assert handler._s3_client == mock_s3_client
        mock_boto3.Session.assert_called_once()
        mock_session.client.assert_called_once_with("s3")

    def test_init_with_client(self) -> None:
        """Test initialization with provided S3 client."""
        mock_s3_client = Mock()
        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)

        assert handler._s3_client == mock_s3_client

    def test_generate_presigned_url_success(self) -> None:
        """Test successful generation of presigned URL."""
        mock_s3_client = Mock()
        expected_url = "https://my-bucket.s3.amazonaws.com/test.txt?signature=abc123"
        mock_s3_client.generate_presigned_url.return_value = expected_url

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        result = handler.generate_presigned_url("my-bucket", "test.txt")

        assert result == expected_url
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "test.txt"},
            ExpiresIn=3600,
        )

    def test_generate_presigned_url_custom_expiration(self) -> None:
        """Test generation of presigned URL with custom expiration."""
        mock_s3_client = Mock()
        expected_url = "https://my-bucket.s3.amazonaws.com/test.txt?signature=abc123"
        mock_s3_client.generate_presigned_url.return_value = expected_url

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        result = handler.generate_presigned_url("my-bucket", "test.txt", expires_in=7200)

        assert result == expected_url
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "test.txt"},
            ExpiresIn=7200,
        )

    def test_generate_presigned_url_exception(self) -> None:
        """Test presigned URL generation when S3 operation fails."""
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
            "GeneratePresignedUrl",
        )

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)

        try:
            handler.generate_presigned_url("nonexistent-bucket", "test.txt")
            assert False, "Expected exception to be raised"
        except ClientError as e:
            assert e.response["Error"]["Code"] == "NoSuchBucket"

    def test_parse_presigned_url_standard_format(self) -> None:
        """Test parsing presigned URL in standard format."""
        url = "https://my-bucket.s3.amazonaws.com/my/key/file.txt?signature=xyz"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is not None
        assert result[0] == "my-bucket"
        assert result[1] == "my/key/file.txt"

    def test_parse_presigned_url_regional_format(self) -> None:
        """Test parsing presigned URL with regional endpoint."""
        url = "https://my-bucket.s3.us-west-2.amazonaws.com/my/key/file.txt"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is not None
        assert result[0] == "my-bucket"
        assert result[1] == "my/key/file.txt"

    def test_parse_presigned_url_with_encoded_key(self) -> None:
        """Test parsing presigned URL with URL-encoded key."""
        url = "https://my-bucket.s3.amazonaws.com/my%20key/file%2Bname.txt"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is not None
        assert result[0] == "my-bucket"
        assert result[1] == "my key/file+name.txt"

    def test_parse_presigned_url_invalid_format(self) -> None:
        """Test parsing presigned URL with invalid format."""
        url = "https://example.com/not-an-s3-url"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is None

    def test_parse_presigned_url_exception(self) -> None:
        """Test parsing presigned URL when exception occurs."""
        url = "not-a-valid-url"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is None

    def test_parse_presigned_url_missing_key(self) -> None:
        """Test parsing presigned URL with missing key."""
        url = "https://my-bucket.s3.amazonaws.com/"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is None

    def test_convert_to_data_url_success(self) -> None:
        """Test successful conversion to data URL."""
        mock_s3_client = Mock()
        mock_response = {"Body": Mock(read=Mock(return_value=b"data:image/png;base64,iVBORw0KGgo="))}
        mock_s3_client.get_object.return_value = mock_response

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://my-bucket.s3.amazonaws.com/images/test.txt"

        result = handler.convert_to_data_url(url)

        assert result == "data:image/png;base64,iVBORw0KGgo="
        mock_s3_client.get_object.assert_called_once_with(Bucket="my-bucket", Key="images/test.txt")

    def test_convert_to_data_url_parse_failure(self) -> None:
        """Test conversion to data URL when URL parsing fails."""
        mock_s3_client = Mock()
        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://invalid-url.com/test"

        result = handler.convert_to_data_url(url)

        # Should return original URL on failure
        assert result == url
        mock_s3_client.get_object.assert_not_called()

    def test_convert_to_data_url_s3_exception(self) -> None:
        """Test conversion to data URL when S3 operation fails."""
        mock_s3_client = Mock()
        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "GetObject",
        )

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://my-bucket.s3.amazonaws.com/missing.txt"

        result = handler.convert_to_data_url(url)

        # Should return original URL on failure
        assert result == url

    def test_delete_object_success(self) -> None:
        """Test successful object deletion."""
        mock_s3_client = Mock()
        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://my-bucket.s3.amazonaws.com/images/test.txt"

        result = handler.delete_object(url)

        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(Bucket="my-bucket", Key="images/test.txt")

    def test_delete_object_parse_failure(self) -> None:
        """Test object deletion when URL parsing fails."""
        mock_s3_client = Mock()
        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://invalid-url.com/test"

        result = handler.delete_object(url)

        assert result is False
        mock_s3_client.delete_object.assert_not_called()

    def test_delete_object_s3_exception(self) -> None:
        """Test object deletion when S3 operation fails."""
        mock_s3_client = Mock()
        mock_s3_client.delete_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
            "DeleteObject",
        )

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://my-bucket.s3.amazonaws.com/test.txt"

        result = handler.delete_object(url)

        assert result is False

    def test_parse_presigned_url_with_deep_path(self) -> None:
        """Test parsing presigned URL with deeply nested path."""
        url = "https://test-bucket.s3.amazonaws.com/a/b/c/d/e/file.json"
        result = S3PresignedUrlHandler.parse_presigned_url(url)

        assert result is not None
        assert result[0] == "test-bucket"
        assert result[1] == "a/b/c/d/e/file.json"

    def test_convert_to_data_url_with_large_data(self) -> None:
        """Test conversion with large data URL."""
        mock_s3_client = Mock()
        large_data = "data:image/png;base64," + ("A" * 10000)
        mock_response = {"Body": Mock(read=Mock(return_value=large_data.encode("utf-8")))}
        mock_s3_client.get_object.return_value = mock_response

        handler = S3PresignedUrlHandler(s3_client=mock_s3_client)
        url = "https://my-bucket.s3.amazonaws.com/large-file.txt"

        result = handler.convert_to_data_url(url)

        assert result == large_data
        assert len(result) > 10000
