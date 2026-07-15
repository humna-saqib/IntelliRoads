"""
IntelliRoads – WebSocket manager.

Handles WebSocket connections and broadcasts real-time traffic updates.
"""

from __future__ import annotations

import asyncio
from typing import List

from fastapi import WebSocket, WebSocketDisconnect
from app.core.state_store import InMemoryStateStore
from app.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketManager:
    """
    Manages client WebSocket connections and facilitates real-time broadcasting.
    """

    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        logger.info("WebSocketManager initialised.")

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new client connection.
        """
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            f"Client connected to WebSocket. Total active: {len(self._connections)}"
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Unregister a disconnected client.
        """
        if websocket in self._connections:
            self._connections.remove(websocket)
            logger.info(
                f"Client disconnected from WebSocket. Total active: {len(self._connections)}"
            )

    async def broadcast(self, data: dict) -> None:
        """
        Broadcast a message to all active WebSocket connections.
        """
        if not self._connections:
            return

        logger.debug(f"Broadcasting to {len(self._connections)} connections.")
        inactive_sockets: List[WebSocket] = []

        # Broadcast concurrently
        tasks = []
        for connection in self._connections:
            tasks.append(self._send_json_safe(connection, data, inactive_sockets))

        if tasks:
            await asyncio.gather(*tasks)

        # Cleanup disconnected clients
        for ws in inactive_sockets:
            self.disconnect(ws)

    async def _send_json_safe(
        self, websocket: WebSocket, data: dict, inactive_list: List[WebSocket]
    ) -> None:
        """
        Safely send JSON message to a single connection.
        """
        try:
            await websocket.send_json(data)
        except Exception as exc:
            logger.debug(f"Failed to send to socket: {exc}")
            inactive_list.append(websocket)

    def get_connection_count(self) -> int:
        """
        Return count of active connections.
        """
        return len(self._connections)


async def websocket_endpoint(
    websocket: WebSocket,
    manager: WebSocketManager,
    store: InMemoryStateStore,
) -> None:
    """
    FastAPI endpoint handler for WebSocket stream.
    """
    await manager.connect(websocket)
    try:
        # Send current state immediately on connection
        snapshot = await store.get_full_snapshot()
        await websocket.send_json(snapshot)

        # Keep connection open and listen for client disconnects
        # (Clients don't send data here, they just receive, so we wait for disconnect)
        while True:
            # We use receive_text with a timeout or just wait for messages/disconnect
            # receive_text is block-waiting for messages. If client closes, it raises WebSocketDisconnect
            data = await websocket.receive_text()
            # If client sends anything (e.g. heartbeat/ping), we can just ignore it or reply
            logger.debug(f"Received ping/msg from WS client: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client.")
    except Exception as exc:
        logger.warning(f"Error in WebSocket endpoint loop: {exc}")
    finally:
        manager.disconnect(websocket)
