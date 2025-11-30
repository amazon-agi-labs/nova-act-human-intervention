"""Credentials providers for AWS service authentication."""

from amzn_nova_act_human_intervention_client.credentials.assumed_role import AssumedRoleCredentialsProvider
from amzn_nova_act_human_intervention_client.credentials.base import CredentialsProvider

__all__ = [
    "CredentialsProvider",
    "AssumedRoleCredentialsProvider",
]
