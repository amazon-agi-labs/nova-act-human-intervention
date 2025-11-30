"""WebSocket executor package.

Provides WebSocket-based human intervention capabilities including:
- WebSocket connection/disconnection handlers for Lambda
- WebSocket service for managing real-time connections
- Integration with API Gateway WebSocket APIs
"""

from amzn_nova_act_human_intervention.executors.websocket.handlers import (
    start_hitl_flow,
    websocket_connect,
    websocket_disconnect,
)
from amzn_nova_act_human_intervention.executors.websocket.service import WebSocketService

__all__ = [
    "WebSocketService",
    "start_hitl_flow",
    "websocket_connect",
    "websocket_disconnect",
]
