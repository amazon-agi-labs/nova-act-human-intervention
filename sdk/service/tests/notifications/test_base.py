"""Tests for notifications base module."""

from abc import ABC

import pytest
from amzn_nova_act_human_intervention_common import EmailContactInfo, UseCase

from amzn_nova_act_human_intervention.notifications.base import BaseNotifier, NotificationData, NotificationType


class TestNotificationData:
    """Test cases for NotificationData model."""

    def test_notification_data_creation(self) -> None:
        """Test creating NotificationData with all fields."""
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="test message",
        )

        assert data.recipients == [email_contact]
        assert data.workflow_run_id == "wf-123"
        assert data.session_id == "sess-123"
        assert data.act_id == "act-123"
        assert data.use_case == UseCase.UI_TAKEOVER
        assert data.notification_type == NotificationType.REQUEST_SENT
        assert data.expiration_time_utc == "2025-10-21T12:00:00Z"
        assert data.temporary_link == "https://example.com/link"
        assert data.message == "test message"

    def test_notification_data_approval(self) -> None:
        """Test creating NotificationData for Approval use case."""
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.APPROVAL,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="Approve this request?",
        )

        assert data.recipients == [email_contact]
        assert data.use_case == UseCase.APPROVAL
        assert data.notification_type == NotificationType.REQUEST_SENT
        assert data.message == "Approve this request?"


class ConcreteNotifier(BaseNotifier):
    """Concrete implementation for testing BaseNotifier."""

    def send(self, data: NotificationData) -> bool:
        return True


class TestBaseNotifier:
    """Test cases for BaseNotifier abstract class."""

    def test_is_abstract_class(self) -> None:
        """Test that BaseNotifier is an abstract class."""
        assert issubclass(BaseNotifier, ABC)

    def test_cannot_instantiate_directly(self) -> None:
        """Test that BaseNotifier cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseNotifier()  # type: ignore

    def test_concrete_implementation(self) -> None:
        """Test concrete implementation of BaseNotifier."""
        notifier = ConcreteNotifier()
        email_contact = EmailContactInfo(to_email_address="user@example.com", from_email_address="noreply@example.com")
        data = NotificationData(
            recipients=[email_contact],
            workflow_run_id="wf-123",
            session_id="sess-123",
            act_id="act-123",
            use_case=UseCase.UI_TAKEOVER,
            notification_type=NotificationType.REQUEST_SENT,
            expiration_time_utc="2025-10-21T12:00:00Z",
            temporary_link="https://example.com/link",
            message="test message",
        )

        result = notifier.send(data)
        assert result is True

    def test_abstract_methods_exist(self) -> None:
        """Test that all required abstract methods exist."""
        abstract_methods = BaseNotifier.__abstractmethods__
        expected_methods = {"send"}
        assert abstract_methods == expected_methods
