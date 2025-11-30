"""DynamoDB Streams handlers for cleanup operations.

This module contains Lambda handlers that process DynamoDB Stream events
for cleanup tasks such as deleting expired S3 objects when execution records expire.
"""

import os
from http import HTTPStatus
from logging import Logger
from typing import Optional

import boto3
from amzn_nova_act_human_intervention_common import ExecutionItem, JSONType, LoggingConfig
from aws_lambda_powertools.utilities.data_classes import DynamoDBStreamEvent, event_source
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import DynamoDBRecordEventName
from aws_lambda_powertools.utilities.typing import LambdaContext

from amzn_nova_act_human_intervention.notifications.notification_factory import NotificationFactory

logger: Logger = LoggingConfig.get_logger(__name__)
s3_client = boto3.client("s3")

# Initialize NotificationFactory for sending expiration notifications
# This is optional - if Slack credentials are not configured, notifications will be skipped
notification_factory: Optional[NotificationFactory]
try:
    notification_factory = NotificationFactory()
    logger.info("NotificationFactory initialized successfully for expiration notifications")
except Exception as e:
    logger.info(f"NotificationFactory not configured: {e}. Expiration notifications will be skipped.")
    logger.debug(f"Full error details: {e}", exc_info=True)
    notification_factory = None


@event_source(data_class=DynamoDBStreamEvent)
def cleanup_expired_spa_objects(event: DynamoDBStreamEvent, context: LambdaContext) -> JSONType:
    """Lambda handler for DynamoDB stream events to cleanup expired SPA HTML files and send notifications.

    WHY THIS CONSUMER IS NEEDED:
    ============================
    When a human intervention session expires (based on DynamoDB TTL on the executions table),
    two things need to happen:
    1. The corresponding SPA HTML file in S3 should be deleted for security and cost reasons
    2. Users should be notified via Slack that the request has expired

    However, S3 lifecycle rules have a MINIMUM expiration period of 24 hours, which means:
    - Session TTL might be 2-4 hours, but S3 objects would remain for at least 24 hours
    - This creates a security gap where expired sessions remain accessible
    - CloudFront URLs have NO expiration (unlike S3 presigned URLs), so the SPA HTML
      remains visible to anyone with the link as long as the S3 object exists

    CLOUDFRONT URL BEHAVIOR:
    ========================
    CloudFront distribution URLs (https://dxxxxx.cloudfront.net/path) do NOT have any
    expiration mechanism built into the URL itself. The only way to prevent access is to:
    1. Delete the underlying S3 object (which this handler does), OR
    2. Invalidate the CloudFront cache (costs money and takes time)

    This is different from S3 presigned URLs which have query string parameters that expire.
    With CloudFront, the URL remains valid forever as long as the S3 object exists. Therefore,
    timely deletion of expired SPA objects is critical for security.

    HOW IT WORKS:
    =============
    1. DynamoDB TTL automatically deletes expired records from the executions table
    2. DynamoDB Streams captures these DELETE events
    3. This Lambda function processes the stream, extracts the S3 object key from the
       execution record, and deletes the corresponding SPA HTML file
    4. Sends expiration notification to Slack (if configured) to inform users
    5. This ensures SPA objects are deleted and users are notified within seconds/minutes
       of session expiry, not 24 hours later

    Args:
        event: DynamoDB stream event containing records of deleted execution items
        context: Lambda execution context

    Returns:
        Dictionary with statusCode and message

    Note:
        - Only processes REMOVE events (when DynamoDB TTL deletes expired items)
        - Only deletes SPA files for Approval use case (UI Takeover doesn't use SPAs)
        - Expiration notifications are sent as threaded replies if thread_ts is available
    """
    bucket_name = os.environ.get("SPA_BUCKET_NAME")
    if not bucket_name:
        error_msg = "SPA_BUCKET_NAME environment variable not set"
        logger.error(error_msg)
        return {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR, "message": error_msg}

    for record in event.records:
        # Only process REMOVE events (when TTL deletes expired items)
        # Note: Event source mapping filters ensure only REMOVE events arrive
        if record.event_name != DynamoDBRecordEventName.REMOVE:
            logger.debug(f"Skipping non-REMOVE event: {record.event_name}")
            continue

        # Extract the old image (deleted item data)
        old_image_dict = record.dynamodb.old_image if record.dynamodb else None
        if not old_image_dict:
            logger.warning(f"No old_image found for REMOVE event: {record.event_id}")
            continue

        try:
            # Deserialize DynamoDB record to ExecutionItem
            execution_item = ExecutionItem(**old_image_dict)

            # Construct S3 key from eventId
            # SPA files are stored as: {eventId}.html
            s3_key = f"{execution_item.eventId}.html"

            logger.info(f"Deleting expired SPA object: s3://{bucket_name}/{s3_key}")

            # Delete the S3 object
            s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            logger.info(f"Successfully deleted expired SPA: {s3_key}")

            # Send expiration notification to Slack only if no action was taken
            # Skip notification if executionStatus indicates user has already taken action
            # (e.g., COMPLETED: user approved/denied, TERMINATED: user stopped workflow)
            if execution_item.executionStatus.has_user_action():
                logger.info(
                    f"Skipping expiration notification for eventId: {execution_item.eventId} "
                    f"- user already took action (executionStatus: {execution_item.executionStatus})"
                )
            elif not notification_factory:
                logger.debug("NotificationFactory not configured, skipping expiration notification")
            else:
                try:
                    logger.info(
                        f"Sending expiration notification for eventId: {execution_item.eventId} "
                        f"(executionStatus: {execution_item.executionStatus})"
                    )
                    notification_sent = notification_factory.send_expiration_notification(execution_item)
                    if notification_sent:
                        logger.info(f"Expiration notification sent successfully for eventId: {execution_item.eventId}")
                    else:
                        logger.warning(f"Expiration notification failed for eventId: {execution_item.eventId}")
                except Exception as notif_error:
                    logger.error(f"Failed to send expiration notification: {notif_error}", exc_info=True)

            success_msg = f"Successfully deleted expired SPA: {s3_key}"
            return {"statusCode": HTTPStatus.OK, "message": success_msg}

        except Exception as e:
            event_id = old_image_dict.get("eventId", "unknown") if old_image_dict else "unknown"
            error_msg = f"Failed to delete SPA object for eventId {event_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR, "message": error_msg}

    # No records to process
    logger.info("No SPA objects to delete in this batch")
    return {"statusCode": HTTPStatus.OK, "message": "No SPA objects to delete"}
