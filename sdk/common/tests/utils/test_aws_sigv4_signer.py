"""Unit tests for AWSSigV4Signer."""

from unittest.mock import Mock, patch

from botocore.credentials import Credentials  # type: ignore[import-untyped]

from amzn_nova_act_human_intervention_common import AWSSigV4Signer


class TestAWSSigV4Signer:
    """Test cases for AWSSigV4Signer class."""

    def test_init(self):
        """Test initialization."""
        signer = AWSSigV4Signer(region="us-east-1", service="execute-api")

        assert signer.region == "us-east-1"
        assert signer.service == "execute-api"

    def test_sign_websocket_url_with_credentials_object(self):
        """Test WebSocket URL signing with Credentials object."""
        signer = AWSSigV4Signer(region="us-east-1", service="execute-api")

        mock_credentials = Mock(spec=Credentials)
        mock_credentials.access_key = "test-access-key"
        mock_credentials.secret_key = "test-secret-key"
        mock_credentials.token = "test-token"

        with (
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest") as mock_request,
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth") as mock_auth,
        ):
            mock_request_instance = Mock()
            mock_request_instance.url = (
                "https://api-id.execute-api.us-east-1.amazonaws.com/stage?X-Amz-Algorithm=AWS4-HMAC-SHA256"
            )
            mock_request.return_value = mock_request_instance

            mock_signer = Mock()
            mock_auth.return_value = mock_signer

            websocket_url = "wss://api-id.execute-api.us-east-1.amazonaws.com/stage"
            signed_url = signer.sign_websocket_url(websocket_url, mock_credentials, expires_in=1800)

            # Verify HTTP conversion for signing
            mock_request.assert_called_once_with(
                method="GET", url="https://api-id.execute-api.us-east-1.amazonaws.com/stage"
            )
            mock_auth.assert_called_once_with(mock_credentials, "execute-api", "us-east-1", expires=1800)
            mock_signer.add_auth.assert_called_once_with(mock_request_instance)

            # Verify WebSocket scheme conversion back
            assert signed_url.startswith("wss://")
            assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in signed_url

    def test_sign_websocket_url_with_credentials_only(self):
        """Test WebSocket URL signing with Credentials object only."""
        signer = AWSSigV4Signer(region="us-west-2", service="execute-api")

        mock_credentials = Mock(spec=Credentials)
        mock_credentials.access_key = "test-access-key"
        mock_credentials.secret_key = "test-secret-key"
        mock_credentials.token = "test-token"

        with (
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest") as mock_request,
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth") as mock_auth,
        ):
            mock_request_instance = Mock()
            mock_request_instance.url = "https://api-id.execute-api.us-west-2.amazonaws.com/stage?signed=true"
            mock_request.return_value = mock_request_instance

            mock_signer_instance = Mock()
            mock_auth.return_value = mock_signer_instance

            websocket_url = "wss://api-id.execute-api.us-west-2.amazonaws.com/stage"
            signed_url = signer.sign_websocket_url(websocket_url, mock_credentials)

            # Verify default expiration is used
            mock_auth.assert_called_once_with(mock_credentials, "execute-api", "us-west-2", expires=3600)

            assert signed_url.startswith("wss://")

    def test_sign_websocket_url_ws_to_http_conversion(self):
        """Test WebSocket to HTTP URL conversion for signing."""
        signer = AWSSigV4Signer(region="us-east-1", service="execute-api")
        mock_credentials = Mock(spec=Credentials)

        with patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest") as mock_request:
            mock_request_instance = Mock()
            mock_request_instance.url = "http://api-id.execute-api.us-east-1.amazonaws.com/stage?signed=true"
            mock_request.return_value = mock_request_instance

            with patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth"):
                # Test ws:// to http:// conversion
                websocket_url = "ws://api-id.execute-api.us-east-1.amazonaws.com/stage"
                signed_url = signer.sign_websocket_url(websocket_url, mock_credentials)

                # Verify HTTP URL was used for signing
                mock_request.assert_called_with(
                    method="GET", url="http://api-id.execute-api.us-east-1.amazonaws.com/stage"
                )

                # Verify conversion back to WebSocket
                assert signed_url.startswith("ws://")

    def test_sign_websocket_url_custom_expires_in(self):
        """Test WebSocket URL signing with custom expiration."""
        signer = AWSSigV4Signer(region="us-east-1", service="execute-api")
        mock_credentials = Mock(spec=Credentials)

        with (
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest"),
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth") as mock_auth,
        ):
            mock_signer_instance = Mock()
            mock_auth.return_value = mock_signer_instance

            websocket_url = "wss://api-id.execute-api.us-east-1.amazonaws.com/stage"
            signer.sign_websocket_url(websocket_url, mock_credentials, expires_in=7200)

            # Verify custom expiration was used
            mock_auth.assert_called_once_with(mock_credentials, "execute-api", "us-east-1", expires=7200)

    def test_sign_websocket_url_with_none_url(self):
        """Test WebSocket URL signing when signed URL is None."""
        signer = AWSSigV4Signer(region="us-east-1", service="execute-api")
        mock_credentials = Mock(spec=Credentials)

        with (
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest") as mock_request,
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth"),
        ):
            mock_request_instance = Mock()
            mock_request_instance.url = None
            mock_request.return_value = mock_request_instance

            websocket_url = "wss://api-id.execute-api.us-east-1.amazonaws.com/stage"

            try:
                signer.sign_websocket_url(websocket_url, mock_credentials)
                assert False, "Expected ValueError to be raised"
            except ValueError as e:
                assert str(e) == "Signed URL is None"

    def test_sign_websocket_url_with_existing_query_params(self):
        """Test WebSocket URL signing with existing query parameters."""
        signer = AWSSigV4Signer(region="us-east-1", service="execute-api")
        mock_credentials = Mock(spec=Credentials)

        with (
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest") as mock_request,
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth"),
        ):
            mock_request_instance = Mock()
            mock_request_instance.url = "https://api.execute-api.us-east-1.amazonaws.com/stage?foo=bar&signed=true"
            mock_request.return_value = mock_request_instance

            websocket_url = "wss://api.execute-api.us-east-1.amazonaws.com/stage?foo=bar"
            signed_url = signer.sign_websocket_url(websocket_url, mock_credentials)

            # Verify HTTP conversion with query params preserved
            mock_request.assert_called_once_with(
                method="GET", url="https://api.execute-api.us-east-1.amazonaws.com/stage?foo=bar"
            )

            # Verify WebSocket scheme and query params
            assert signed_url.startswith("wss://")
            assert "foo=bar" in signed_url

    def test_sign_websocket_url_with_complex_path(self):
        """Test WebSocket URL signing with complex path."""
        signer = AWSSigV4Signer(region="ap-south-1", service="execute-api")
        mock_credentials = Mock(spec=Credentials)

        with (
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest") as mock_request,
            patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth"),
        ):
            mock_request_instance = Mock()
            mock_request_instance.url = "https://api.execute-api.ap-south-1.amazonaws.com/prod/v1/connect?signed=true"
            mock_request.return_value = mock_request_instance

            websocket_url = "wss://api.execute-api.ap-south-1.amazonaws.com/prod/v1/connect"
            signed_url = signer.sign_websocket_url(websocket_url, mock_credentials)

            # Verify complex path handling
            mock_request.assert_called_once_with(
                method="GET", url="https://api.execute-api.ap-south-1.amazonaws.com/prod/v1/connect"
            )

            assert signed_url.startswith("wss://")
            assert "/prod/v1/connect" in signed_url

    def test_sign_websocket_url_different_regions(self):
        """Test WebSocket URL signing with different AWS regions."""
        regions = ["us-east-1", "eu-west-1", "ap-northeast-1"]

        for region in regions:
            signer = AWSSigV4Signer(region=region, service="execute-api")
            mock_credentials = Mock(spec=Credentials)

            with (
                patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.AWSRequest"),
                patch("amzn_nova_act_human_intervention_common.utils.aws_sigv4_signer.SigV4QueryAuth") as mock_auth,
            ):
                mock_signer_instance = Mock()
                mock_auth.return_value = mock_signer_instance

                websocket_url = f"wss://api-id.execute-api.{region}.amazonaws.com/stage"
                signer.sign_websocket_url(websocket_url, mock_credentials)

                # Verify region is correctly passed to signer
                mock_auth.assert_called_once_with(mock_credentials, "execute-api", region, expires=3600)
