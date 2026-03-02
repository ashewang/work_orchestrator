"""Simple in-process event bus for real-time notifications."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Subscribers: list of callbacks that receive (event_type, payload_dict)
_subscribers: list[Callable[[str, dict], None]] = []
_lock = threading.Lock()


def subscribe(callback: Callable[[str, dict], None]) -> Callable[[], None]:
    """Subscribe to events. Returns an unsubscribe function."""
    with _lock:
        _subscribers.append(callback)

    def unsub():
        with _lock:
            try:
                _subscribers.remove(callback)
            except ValueError:
                pass

    return unsub


def publish(event_type: str, payload: dict) -> None:
    """Publish an event to all subscribers. Thread-safe."""
    with _lock:
        subs = list(_subscribers)

    for cb in subs:
        try:
            cb(event_type, payload)
        except Exception:
            logger.exception("Error in event subscriber")


def to_json(event_type: str, payload: dict) -> str:
    """Serialize an event to JSON."""
    return json.dumps({"type": event_type, **payload})
