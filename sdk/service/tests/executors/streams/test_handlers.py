"""Tests for DynamoDB Streams handlers module."""

import os
from unittest.mock import Mock, patch

from aws_lambda_powertools.utilities.data_classes import DynamoDBStreamEvent

from amzn_nova_act_human_intervention.executors.streams.handlers import cleanup_expired_spa_objects


class TestCleanupExpiredSpaObjects:
    """Test cases for cleanup_expired_spa_objects handler."""

    @staticmethod
    def get_test_event_data() -> dict:
        """Get the standard test event data for all tests."""
        return {
            "Records": [
                {
                    "eventID": "fdd4a9f590922925e677c95c8f0c1213",
                    "eventName": "REMOVE",
                    "eventVersion": "1.1",
                    "eventSource": "aws:dynamodb",
                    "awsRegion": "us-west-2",
                    "dynamodb": {
                        "ApproximateCreationDateTime": 1761338456,
                        "Keys": {"eventId": {"S": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}},
                        "OldImage": {
                            "eventId": {"S": "f47ac10b-58cc-4372-a567-0e02b2c3d479"},
                            "executionEndpoint": {"S": "wss://api.example.com/ws"},
                            "executionStatus": {"S": "COMPLETED"},
                            "query": {"S": "Do you approve this purchase order for $1,500?"},
                            "actId": {"S": "abcdef12-3456-7890-abcd-ef1234567890"},
                            "sessionId": {"S": "87654321-4321-4321-4321-210987654321"},
                            "ttl": {"N": "1703184000"},
                            "timeout": {"N": "86400"},
                            "approvalAction": {"S": "APPROVE"},
                            "createdAt": {"N": "1703097600"},
                            "executionArn": {
                                "S": "arn:aws:states:us-east-1:123456789012:execution:MyStateMachine:execution-name"
                            },
                            "options": {
                                "L": [
                                    {"M": {"action": {"S": "APPROVE"}, "label": {"S": "Approve"}}},
                                    {"M": {"action": {"S": "DENY"}, "label": {"S": "Cancel"}}},
                                ]
                            },
                            "connectionId": {"S": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
                            "notificationRecipients": {
                                "L": [
                                    {
                                        "M": {
                                            "channel": {"S": "Slack"},
                                            "contact_info": {
                                                "M": {
                                                    "type": {"S": "slack"},
                                                    "channel": {"S": "#test-channel"},
                                                    "target": {"S": "@testuser"},
                                                    "target_type": {"S": "user"},
                                                }
                                            },
                                        }
                                    }
                                ]
                            },
                            "interventionType": {"S": "Approval"},
                            "mostRecentScreenshot": {"S": "data:image/png;base64,iVBRU5ErkJggg=="},
                            "workflowRunId": {"S": "12345678-1234-1234-1234-123456789012"},
                            "slackThreadTs": {"S": "1234567890.123456"},
                            "updatedAt": {"N": "1703097650"},
                        },
                        "SequenceNumber": "52433000004465437221390626",
                        "SizeBytes": 762,
                        "StreamViewType": "OLD_IMAGE",
                    },
                    "userIdentity": {"principalId": "dynamodb.amazonaws.com", "type": "Service"},
                    "eventSourceARN": "arn:aws:dynamodb:us-west-2:192025382688:table/tableName/stream/...",
                }
            ]
        }

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory")
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_success_with_completed_status(
        self, mock_s3_client: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test successful cleanup of expired SPA object when status is COMPLETED (no notification sent)."""
        mock_notification_factory.send_expiration_notification.return_value = True

        event_data = self.get_test_event_data()
        # executionStatus is already "COMPLETED" in the test data
        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        assert result["statusCode"] == 200
        assert "Successfully deleted expired SPA: f47ac10b-58cc-4372-a567-0e02b2c3d479.html" in result["message"]
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-spa-bucket", Key="f47ac10b-58cc-4372-a567-0e02b2c3d479.html"
        )
        # Verify expiration notification was NOT sent because status is COMPLETED
        mock_notification_factory.send_expiration_notification.assert_not_called()

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory")
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_success_with_pending_status(
        self, mock_s3_client: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test successful cleanup of expired SPA object when status is not COMPLETED (notification sent)."""
        mock_notification_factory.send_expiration_notification.return_value = True

        event_data = self.get_test_event_data()
        # Change executionStatus to PENDING_HUMAN_INPUT (or any status other than COMPLETED)
        event_data["Records"][0]["dynamodb"]["OldImage"]["executionStatus"]["S"] = "PENDING_HUMAN_INPUT"
        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        assert result["statusCode"] == 200
        assert "Successfully deleted expired SPA: f47ac10b-58cc-4372-a567-0e02b2c3d479.html" in result["message"]
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-spa-bucket", Key="f47ac10b-58cc-4372-a567-0e02b2c3d479.html"
        )
        # Verify expiration notification WAS sent because status is not COMPLETED
        mock_notification_factory.send_expiration_notification.assert_called_once()

    def test_cleanup_expired_spa_objects_missing_bucket_env(self) -> None:
        """Test handler when SPA_BUCKET_NAME environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            event = DynamoDBStreamEvent(self.get_test_event_data())
            context = Mock()

            result = cleanup_expired_spa_objects(event, context)

            assert result["statusCode"] == 500
            assert "SPA_BUCKET_NAME environment variable not set" in result["message"]

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    def test_cleanup_expired_spa_objects_no_records(self) -> None:
        """Test handler with no records to process."""
        event_data = self.get_test_event_data()
        event_data["Records"] = []  # Empty records
        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        assert result["statusCode"] == 200
        assert result["message"] == "No SPA objects to delete"

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory")
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_s3_error(self, mock_s3_client: Mock, mock_notification_factory: Mock) -> None:
        """Test handler when S3 delete operation fails."""
        mock_s3_client.delete_object.side_effect = Exception("S3 error")

        event = DynamoDBStreamEvent(self.get_test_event_data())
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        assert result["statusCode"] == 500
        assert (
            "Failed to delete SPA object for eventId f47ac10b-58cc-4372-a567-0e02b2c3d479: S3 error"
            in result["message"]
        )
        # Notification should not be called if S3 delete fails
        mock_notification_factory.send_expiration_notification.assert_not_called()

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_non_remove_event(self, mock_s3_client: Mock) -> None:
        """Test handler skips non-REMOVE events (INSERT, MODIFY)."""
        event_data = self.get_test_event_data()
        # Change event to INSERT instead of REMOVE
        event_data["Records"][0]["eventName"] = "INSERT"

        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        # Should skip the INSERT event and return success with no deletion
        assert result["statusCode"] == 200
        assert result["message"] == "No SPA objects to delete"
        # S3 delete should NOT be called for non-REMOVE events
        mock_s3_client.delete_object.assert_not_called()

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_missing_old_image(self, mock_s3_client: Mock) -> None:
        """Test handler when REMOVE event has no old_image data."""
        event_data = self.get_test_event_data()
        # Remove OldImage from the record
        del event_data["Records"][0]["dynamodb"]["OldImage"]

        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        # Should skip the record without old_image and return success
        assert result["statusCode"] == 200
        assert result["message"] == "No SPA objects to delete"
        # S3 delete should NOT be called when old_image is missing
        mock_s3_client.delete_object.assert_not_called()

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory")
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_notification_failure(
        self, mock_s3_client: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test that S3 cleanup succeeds even if notification fails."""
        mock_notification_factory.send_expiration_notification.side_effect = Exception("Notification error")

        event_data = self.get_test_event_data()
        # Change executionStatus to PENDING_HUMAN_INPUT so notification is attempted
        event_data["Records"][0]["dynamodb"]["OldImage"]["executionStatus"]["S"] = "PENDING_HUMAN_INPUT"
        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        # Should still succeed even if notification fails
        assert result["statusCode"] == 200
        assert "Successfully deleted expired SPA: f47ac10b-58cc-4372-a567-0e02b2c3d479.html" in result["message"]
        # S3 delete should have been called
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-spa-bucket", Key="f47ac10b-58cc-4372-a567-0e02b2c3d479.html"
        )
        # Notification should have been attempted (because status is not COMPLETED)
        mock_notification_factory.send_expiration_notification.assert_called_once()

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_notification_factory_not_initialized(self, mock_s3_client: Mock) -> None:
        """Test that S3 cleanup succeeds even if NotificationFactory is not initialized."""
        # Set notification_factory to None to simulate initialization failure
        with patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory", None):
            event_data = self.get_test_event_data()
            event = DynamoDBStreamEvent(event_data)
            context = Mock()

            result = cleanup_expired_spa_objects(event, context)

            # Should still succeed even if notification_factory is None
            assert result["statusCode"] == 200
            assert "Successfully deleted expired SPA: f47ac10b-58cc-4372-a567-0e02b2c3d479.html" in result["message"]
            # S3 delete should have been called
            mock_s3_client.delete_object.assert_called_once_with(
                Bucket="test-spa-bucket", Key="f47ac10b-58cc-4372-a567-0e02b2c3d479.html"
            )

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory")
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_notification_send_fails(
        self, mock_s3_client: Mock, mock_notification_factory: Mock
    ) -> None:
        """Test when notification send returns False (failure case)."""
        # Mock send_expiration_notification to return False (failure)
        mock_notification_factory.send_expiration_notification.return_value = False

        event_data = self.get_test_event_data()
        # Change executionStatus to PENDING_HUMAN_INPUT so notification is attempted
        event_data["Records"][0]["dynamodb"]["OldImage"]["executionStatus"]["S"] = "PENDING_HUMAN_INPUT"
        event = DynamoDBStreamEvent(event_data)
        context = Mock()

        result = cleanup_expired_spa_objects(event, context)

        # Should still succeed even if notification send returns False
        assert result["statusCode"] == 200
        assert "Successfully deleted expired SPA: f47ac10b-58cc-4372-a567-0e02b2c3d479.html" in result["message"]
        # S3 delete should have been called
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-spa-bucket", Key="f47ac10b-58cc-4372-a567-0e02b2c3d479.html"
        )
        # Notification should have been attempted
        mock_notification_factory.send_expiration_notification.assert_called_once()

    @patch.dict("os.environ", {"SPA_BUCKET_NAME": "test-spa-bucket"})
    @patch("amzn_nova_act_human_intervention.executors.streams.handlers.s3_client")
    def test_cleanup_expired_spa_objects_notification_factory_not_initialized_pending_status(
        self, mock_s3_client: Mock
    ) -> None:
        """Test notification factory not configured with pending status (debug log case)."""
        # Set notification_factory to None to simulate initialization failure
        with patch("amzn_nova_act_human_intervention.executors.streams.handlers.notification_factory", None):
            event_data = self.get_test_event_data()
            # Change executionStatus to PENDING_HUMAN_INPUT (not COMPLETED)
            event_data["Records"][0]["dynamodb"]["OldImage"]["executionStatus"]["S"] = "PENDING_HUMAN_INPUT"
            event = DynamoDBStreamEvent(event_data)
            context = Mock()

            result = cleanup_expired_spa_objects(event, context)

            # Should still succeed even if notification_factory is None
            assert result["statusCode"] == 200
            assert "Successfully deleted expired SPA: f47ac10b-58cc-4372-a567-0e02b2c3d479.html" in result["message"]
            # S3 delete should have been called
            mock_s3_client.delete_object.assert_called_once_with(
                Bucket="test-spa-bucket", Key="f47ac10b-58cc-4372-a567-0e02b2c3d479.html"
            )
