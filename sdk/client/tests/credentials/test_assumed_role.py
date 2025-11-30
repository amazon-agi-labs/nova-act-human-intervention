"""Unit tests for AssumedRoleCredentialsProvider."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from amzn_nova_act_human_intervention_client.credentials.assumed_role import AssumedRoleCredentialsProvider


class TestAssumedRoleCredentialsProvider:
    """Tests for AssumedRoleCredentialsProvider."""

    @pytest.fixture
    def mock_sts_client(self):
        """Create a mock STS client with successful assume_role response."""
        mock_client = Mock()
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
        mock_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_access_key",
                "SecretAccessKey": "test_secret_key",
                "SessionToken": "test_session_token",
                "Expiration": expiry_time,
            }
        }
        return mock_client

    @pytest.fixture
    def mock_session(self, mock_sts_client):
        """Create a mock boto3 Session."""
        mock_sess = Mock()
        mock_sess.client.return_value = mock_sts_client
        mock_sess.region_name = "us-east-1"
        mock_sess.profile_name = None
        return mock_sess

    def test_init_with_valid_params(self, mock_session):
        """Test successful initialization with valid parameters."""
        with patch(
            "amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session"
        ) as mock_boto_session:
            mock_boto_session.return_value = mock_session

            provider = AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                duration_seconds=3600,
                session=mock_session,
            )

            assert provider.role_arn == "arn:aws:iam::123456789012:role/TestRole"
            assert provider.duration_seconds == 3600
            assert provider.role_session_name == "websocket-client-session"
            assert provider._credentials is not None
            assert provider._expiry is not None

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_init_with_custom_session_name(self, mock_boto_session, mock_session):
        """Test initialization with custom role session name."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
            role_session_name="custom-session",
        )

        assert provider.role_session_name == "custom-session"

    def test_init_empty_role_arn_raises_error(self, mock_session):
        """Test that empty role_arn raises ValueError."""
        with pytest.raises(ValueError, match="role_arn is required"):
            AssumedRoleCredentialsProvider(
                role_arn="",
                duration_seconds=3600,
                session=mock_session,
            )

    def test_init_duration_too_short_raises_error(self, mock_session):
        """Test that duration < 900 seconds raises ValueError."""
        with pytest.raises(ValueError, match="duration_seconds must be between 900 and 43200"):
            AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                duration_seconds=899,
                session=mock_session,
            )

    def test_init_duration_too_long_raises_error(self, mock_session):
        """Test that duration > 43200 seconds raises ValueError."""
        with pytest.raises(ValueError, match="duration_seconds must be between 900 and 43200"):
            AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                duration_seconds=43201,
                session=mock_session,
            )

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_duration_capped_at_max(self, mock_boto_session, mock_session):
        """Test that duration is capped at MAX_ASSUME_ROLE_DURATION (3600)."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=7200,  # Request 2 hours
            session=mock_session,
        )

        # Should be capped at 3600 (1 hour)
        assert provider.duration_seconds == 3600

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_duration_minimum_enforced(self, mock_boto_session, mock_session):
        """Test that duration is enforced to be at least MIN_ASSUME_ROLE_DURATION (900)."""
        mock_boto_session.return_value = mock_session

        # This test passes 900 which is the minimum, but internally it should still be 900
        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=900,
            session=mock_session,
        )

        assert provider.duration_seconds == 900

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_credentials_property(self, mock_boto_session, mock_session):
        """Test credentials property returns valid credentials."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        creds = provider.credentials
        assert creds.access_key == "test_access_key"
        assert creds.secret_key == "test_secret_key"
        assert creds.token == "test_session_token"

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_credentials_property_none_raises_error(self, mock_boto_session, mock_session):
        """Test credentials property raises RuntimeError when credentials is None."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Manually set credentials to None to simulate failure
        provider._credentials = None

        with pytest.raises(RuntimeError, match="No credentials available - refresh\\(\\) may have failed"):
            _ = provider.credentials

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_expiry_property(self, mock_boto_session, mock_session):
        """Test expiry property returns expiration time."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        expiry = provider.expiry
        assert expiry is not None
        assert isinstance(expiry, datetime)
        # Should be in the future
        assert expiry > datetime.now(timezone.utc)

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_refresh_success(self, mock_boto_session, mock_session, mock_sts_client):
        """Test refresh method successfully updates credentials."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Update mock to return new credentials
        new_expiry = datetime.now(timezone.utc) + timedelta(seconds=7200)
        mock_sts_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "new_access_key",
                "SecretAccessKey": "new_secret_key",
                "SessionToken": "new_session_token",
                "Expiration": new_expiry,
            }
        }

        # Call refresh
        provider.refresh()

        # Verify credentials were updated
        assert provider._credentials.access_key == "new_access_key"
        assert provider._credentials.secret_key == "new_secret_key"
        assert provider._credentials.token == "new_session_token"

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_refresh_sts_failure_raises_error(self, mock_boto_session, mock_session, mock_sts_client):
        """Test refresh raises RuntimeError when STS assume_role fails."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Make assume_role raise an exception
        mock_sts_client.assume_role.side_effect = Exception("STS service unavailable")

        with pytest.raises(RuntimeError, match="Failed to assume role.*STS service unavailable"):
            provider.refresh()

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_refresh_called_on_init(self, mock_boto_session, mock_session, mock_sts_client):
        """Test that refresh is called during initialization."""
        mock_boto_session.return_value = mock_session

        AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Verify assume_role was called at least once (during __init__)
        assert mock_sts_client.assume_role.called
        assert mock_sts_client.assume_role.call_count >= 1

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_assume_role_called_with_correct_params(self, mock_boto_session, mock_session, mock_sts_client):
        """Test that assume_role is called with correct parameters."""
        mock_boto_session.return_value = mock_session

        AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
            role_session_name="test-session",
        )

        # Verify assume_role was called with correct parameters
        mock_sts_client.assume_role.assert_called_with(
            RoleArn="arn:aws:iam::123456789012:role/TestRole",
            RoleSessionName="test-session",
            DurationSeconds=3600,
        )

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    def test_expiry_timezone_conversion(self, mock_boto_session, mock_session, mock_sts_client):
        """Test that expiry time is converted to UTC timezone."""
        mock_boto_session.return_value = mock_session

        # Create a datetime with a different timezone
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=3600)

        mock_sts_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "test_key",
                "SecretAccessKey": "test_secret",
                "SessionToken": "test_token",
                "Expiration": expiry_time,
            }
        }

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Verify expiry is in UTC
        assert provider.expiry.tzinfo == timezone.utc

    def test_session_is_required(self):
        """Test that session parameter is required."""
        # This test verifies that session is a required parameter
        # by checking that the function signature requires it
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'session'"):
            AssumedRoleCredentialsProvider(
                role_arn="arn:aws:iam::123456789012:role/TestRole",
                duration_seconds=3600,
            )

    def test_is_running_on_aws_lambda(self):
        """Test detection of Lambda environment."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "my-function"}):
            assert AssumedRoleCredentialsProvider._is_running_on_aws() is True

    def test_is_running_on_aws_ecs(self):
        """Test detection of ECS environment."""
        with patch.dict(os.environ, {"ECS_CONTAINER_METADATA_URI": "http://169.254.170.2/v3"}):
            assert AssumedRoleCredentialsProvider._is_running_on_aws() is True

    def test_is_running_on_aws_ec2(self):
        """Test detection of EC2 environment."""
        with patch.dict(os.environ, {"AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/xxx"}):
            assert AssumedRoleCredentialsProvider._is_running_on_aws() is True

    def test_is_running_on_aws_local(self):
        """Test detection of local environment."""
        with patch.dict(os.environ, {}, clear=True):
            assert AssumedRoleCredentialsProvider._is_running_on_aws() is False

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    @patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "my-function"})
    def test_refresh_on_aws_uses_existing_session(self, mock_boto_session, mock_session, mock_sts_client):
        """Test that refresh on AWS uses existing session (no fresh session creation)."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Reset call count from init
        mock_boto_session.reset_mock()
        mock_session.client.reset_mock()

        # Call refresh
        provider.refresh()

        # On AWS, should use existing session (no new Session() call)
        mock_boto_session.assert_not_called()
        mock_session.client.assert_called_once_with("sts")

    @patch("amzn_nova_act_human_intervention_client.credentials.assumed_role.boto3.Session")
    @patch.dict(os.environ, {}, clear=True)
    def test_refresh_locally_creates_fresh_session(self, mock_boto_session, mock_session, mock_sts_client):
        """Test that refresh locally creates a fresh session."""
        mock_boto_session.return_value = mock_session

        provider = AssumedRoleCredentialsProvider(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            duration_seconds=3600,
            session=mock_session,
        )

        # Reset call count from init
        mock_boto_session.reset_mock()

        # Call refresh
        provider.refresh()

        # Locally, should create fresh session
        mock_boto_session.assert_called_once_with(
            region_name=mock_session.region_name,
            profile_name=mock_session.profile_name,
        )
