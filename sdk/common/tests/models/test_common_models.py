"""Unit tests for common models."""

import pytest
from pydantic import ValidationError

from amzn_nova_act_human_intervention_common.models.common_models import (
    ContactInfo,
    EmailContactInfo,
    NotificationChannel,
    NotificationRecipient,
    SlackContactInfo,
    SlackTargetType,
    UseCase,
)


class TestUseCase:
    """Tests for UseCase enum."""

    def test_approval_value(self):
        assert UseCase.APPROVAL == "Approval"

    def test_ui_takeover_value(self):
        assert UseCase.UI_TAKEOVER == "UITakeover"


class TestNotificationChannel:
    """Tests for NotificationChannel enum."""

    def test_email_value(self):
        assert NotificationChannel.EMAIL == "Email"

    def test_slack_value(self):
        assert NotificationChannel.SLACK == "Slack"


class TestEmailContactInfo:
    """Tests for EmailContactInfo model."""

    def test_create_with_valid_emails(self):
        """Test creating email contact info with valid email addresses."""
        contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        assert contact.type == "email"
        assert contact.to_email_address == "user@example.com"
        assert contact.from_email_address == "noreply@example.com"

    def test_serialization(self):
        """Test serialization to dict."""
        contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = contact.model_dump()
        assert data == {
            "type": "email",
            "to_email_address": "user@example.com",
            "from_email_address": "noreply@example.com",
        }

    def test_deserialization(self):
        """Test deserialization from dict."""
        data = {
            "type": "email",
            "to_email_address": "user@example.com",
            "from_email_address": "noreply@example.com",
        }
        contact = EmailContactInfo(**data)
        assert contact.to_email_address == "user@example.com"
        assert contact.from_email_address == "noreply@example.com"

    def test_missing_to_email_address(self):
        """Test that to_email_address is required."""
        with pytest.raises(ValidationError):
            EmailContactInfo(from_email_address="noreply@example.com")

    def test_missing_from_email_address(self):
        """Test that from_email_address is required."""
        with pytest.raises(ValidationError):
            EmailContactInfo(to_email_address="user@example.com")

    def test_missing_both_email_addresses(self):
        """Test that both email fields are required."""
        with pytest.raises(ValidationError):
            EmailContactInfo()

    def test_valid_email_formats(self):
        """Test various valid email address formats."""
        valid_emails = [
            "user@example.com",
            "user.name@example.com",
            "user+tag@example.co.uk",
            "user_name123@example-domain.com",
            "123user@example.com",
        ]

        for email in valid_emails:
            contact = EmailContactInfo(to_email_address=email, from_email_address="noreply@example.com")
            assert contact.to_email_address == email

    def test_invalid_to_email_format(self):
        """Test that invalid to_email_address format raises ValidationError."""
        invalid_emails = [
            "invalid",
            "invalid@",
            "@example.com",
            "invalid@.com",
            "invalid@domain",
            "invalid @example.com",
            "invalid@exam ple.com",
            "",
        ]

        for invalid_email in invalid_emails:
            with pytest.raises(ValidationError) as exc_info:
                EmailContactInfo(to_email_address=invalid_email, from_email_address="noreply@example.com")
            assert "Invalid email address format" in str(exc_info.value)

    def test_invalid_from_email_format(self):
        """Test that invalid from_email_address format raises ValidationError."""
        invalid_emails = [
            "invalid",
            "invalid@",
            "@example.com",
            "invalid@.com",
            "invalid@domain",
        ]

        for invalid_email in invalid_emails:
            with pytest.raises(ValidationError) as exc_info:
                EmailContactInfo(to_email_address="user@example.com", from_email_address=invalid_email)
            assert "Invalid email address format" in str(exc_info.value)

    def test_both_emails_invalid(self):
        """Test that validation fails when both email addresses are invalid."""
        with pytest.raises(ValidationError) as exc_info:
            EmailContactInfo(to_email_address="invalid", from_email_address="also-invalid")
        # Should have at least one error about invalid email format
        assert "Invalid email address format" in str(exc_info.value)


class TestSlackContactInfo:
    """Tests for SlackContactInfo model."""

    def test_create_user_target(self):
        """Test creating Slack contact info for a user."""
        contact = SlackContactInfo(channel="#general", target="@username", target_type=SlackTargetType.USER)
        assert contact.type == "slack"
        assert contact.channel == "#general"
        assert contact.target == "@username"
        assert contact.target_type == SlackTargetType.USER

    def test_create_usergroup_target(self):
        """Test creating Slack contact info for a user group."""
        contact = SlackContactInfo(
            channel="#incident-response", target="<!subteam^S12345>", target_type=SlackTargetType.USERGROUP
        )
        assert contact.type == "slack"
        assert contact.channel == "#incident-response"
        assert contact.target == "<!subteam^S12345>"
        assert contact.target_type == SlackTargetType.USERGROUP

    def test_default_target_type(self):
        """Test that target_type defaults to 'user'."""
        contact = SlackContactInfo(channel="#general", target="@username")
        assert contact.target_type == SlackTargetType.USER

    def test_serialization(self):
        """Test serialization to dict."""
        contact = SlackContactInfo(channel="#general", target="@username", target_type=SlackTargetType.USER)
        data = contact.model_dump()
        assert data == {
            "type": "slack",
            "channel": "#general",
            "target": "@username",
            "target_type": SlackTargetType.USER,
        }

    def test_deserialization(self):
        """Test deserialization from dict."""
        data = {
            "type": "slack",
            "channel": "#general",
            "target": "@username",
            "target_type": SlackTargetType.USER,
        }
        contact = SlackContactInfo(**data)
        assert contact.channel == "#general"
        assert contact.target == "@username"
        assert contact.target_type == SlackTargetType.USER

    def test_channel_id_format(self):
        """Test using Slack channel ID instead of name."""
        contact = SlackContactInfo(channel="C123456", target="U789012")
        assert contact.channel == "C123456"
        assert contact.target == "U789012"

    def test_missing_required_fields(self):
        """Test that channel and target are required."""
        with pytest.raises(ValidationError):
            SlackContactInfo(channel="#general")

        with pytest.raises(ValidationError):
            SlackContactInfo(target="@username")


class TestNotificationRecipient:
    """Tests for NotificationRecipient model."""

    def test_create_with_email(self):
        """Test creating notification recipient with email contact info."""
        recipient = NotificationRecipient(
            contact_info=EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        )
        assert isinstance(recipient.contact_info, EmailContactInfo)
        assert recipient.contact_info.to_email_address == "user@example.com"
        assert recipient.channel == NotificationChannel.EMAIL

    def test_create_with_slack(self):
        """Test creating notification recipient with Slack contact info."""
        recipient = NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@username"))
        assert isinstance(recipient.contact_info, SlackContactInfo)
        assert recipient.contact_info.channel == "#general"
        assert recipient.contact_info.target == "@username"
        assert recipient.channel == NotificationChannel.SLACK

    def test_channel_property_email(self):
        """Test that channel property returns EMAIL for EmailContactInfo."""
        recipient = NotificationRecipient(
            contact_info=EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        )
        assert recipient.channel == NotificationChannel.EMAIL

    def test_channel_property_slack(self):
        """Test that channel property returns SLACK for SlackContactInfo."""
        recipient = NotificationRecipient(contact_info=SlackContactInfo(channel="#general", target="@username"))
        assert recipient.channel == NotificationChannel.SLACK

    def test_serialization_email(self):
        """Test serialization of email recipient."""
        recipient = NotificationRecipient(
            contact_info=EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        )
        data = recipient.model_dump()
        assert data == {
            "contact_info": {
                "type": "email",
                "to_email_address": "user@example.com",
                "from_email_address": "noreply@example.com",
            }
        }

    def test_serialization_slack(self):
        """Test serialization of Slack recipient."""
        recipient = NotificationRecipient(
            contact_info=SlackContactInfo(channel="#general", target="@username", target_type=SlackTargetType.USER)
        )
        data = recipient.model_dump()
        assert data == {
            "contact_info": {
                "type": "slack",
                "channel": "#general",
                "target": "@username",
                "target_type": SlackTargetType.USER,
            }
        }

    def test_deserialization_email(self):
        """Test deserialization of email recipient using discriminator."""
        data = {
            "contact_info": {
                "type": "email",
                "to_email_address": "user@example.com",
                "from_email_address": "noreply@example.com",
            }
        }
        recipient = NotificationRecipient(**data)
        assert isinstance(recipient.contact_info, EmailContactInfo)
        assert recipient.contact_info.to_email_address == "user@example.com"
        assert recipient.contact_info.from_email_address == "noreply@example.com"
        assert recipient.channel == NotificationChannel.EMAIL

    def test_deserialization_slack(self):
        """Test deserialization of Slack recipient using discriminator."""
        data = {
            "contact_info": {
                "type": "slack",
                "channel": "#general",
                "target": "@username",
                "target_type": SlackTargetType.USER,
            }
        }
        recipient = NotificationRecipient(**data)
        assert isinstance(recipient.contact_info, SlackContactInfo)
        assert recipient.contact_info.channel == "#general"
        assert recipient.contact_info.target == "@username"
        assert recipient.channel == NotificationChannel.SLACK

    def test_discriminator_invalid_type(self):
        """Test that invalid type in discriminator raises error."""
        data = {"contact_info": {"type": "invalid", "some_field": "value"}}
        with pytest.raises(ValidationError) as exc_info:
            NotificationRecipient(**data)
        assert "union_tag_invalid" in str(exc_info.value).lower()

    def test_discriminator_missing_type(self):
        """Test that missing type field raises error."""
        data = {"contact_info": {"to_email_address": "user@example.com", "from_email_address": "noreply@example.com"}}
        with pytest.raises(ValidationError):
            NotificationRecipient(**data)

    def test_round_trip_email(self):
        """Test serialization and deserialization round trip for email."""
        original = NotificationRecipient(
            contact_info=EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        )
        data = original.model_dump()
        restored = NotificationRecipient(**data)

        assert isinstance(restored.contact_info, EmailContactInfo)
        assert restored.contact_info.to_email_address == original.contact_info.to_email_address
        assert restored.contact_info.from_email_address == original.contact_info.from_email_address
        assert restored.channel == original.channel

    def test_round_trip_slack(self):
        """Test serialization and deserialization round trip for Slack."""
        original = NotificationRecipient(
            contact_info=SlackContactInfo(
                channel="#incident-response",
                target="<!subteam^S12345>",
                target_type=SlackTargetType.USERGROUP,
            )
        )
        data = original.model_dump()
        restored = NotificationRecipient(**data)

        assert isinstance(restored.contact_info, SlackContactInfo)
        assert restored.contact_info.channel == original.contact_info.channel
        assert restored.contact_info.target == original.contact_info.target
        assert restored.contact_info.target_type == original.contact_info.target_type
        assert restored.channel == original.channel


class TestContactInfoPolymorphism:
    """Tests for ContactInfo polymorphic behavior."""

    def test_contact_info_is_abstract(self):
        """Test that ContactInfo base class can be instantiated but has generic type."""
        contact = ContactInfo(type="custom")
        assert contact.type == "custom"

    def test_union_type_checking(self):
        """Test that union type correctly identifies subclasses."""
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        slack_contact = SlackContactInfo(channel="#general", target="@username")

        assert isinstance(email_contact, ContactInfo)
        assert isinstance(slack_contact, ContactInfo)
        assert isinstance(email_contact, EmailContactInfo)
        assert isinstance(slack_contact, SlackContactInfo)
        assert not isinstance(email_contact, SlackContactInfo)
        assert not isinstance(slack_contact, EmailContactInfo)
