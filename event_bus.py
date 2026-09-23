"""Small thread-safe event bus for live agent/HUD updates."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from collections import defaultdict
from typing import Any, Callable, Dict, List


class EventBus:
    def __init__(self):
        self._listeners: Dict[str, List[Callable[[Dict[str, Any]], None]]] = defaultdict(list)
        self._lock = threading.RLock()
        self._context: Dict[str, Any] = {}

    def set_context(self, **context: Any) -> None:
        with self._lock:
            self._context.update({key: value for key, value in context.items() if value is not None})

    def subscribe(self, event_name: str, listener: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners[event_name].append(listener)

    def emit(self, event_name: str, payload: Dict[str, Any] | None = None) -> None:
        with self._lock:
            listeners = list(self._listeners.get(event_name, [])) + list(self._listeners.get("*", []))
        with self._lock:
            context = dict(self._context)
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "event_type": event_name,
            "timestamp": datetime.now().isoformat(),
            **context,
            "payload": payload or {},
            "event": event_name,
            **(payload or {}),
        }
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                continue

    def clear(self, event_name: str | None = None) -> None:
        with self._lock:
            if event_name is None:
                self._listeners.clear()
            else:
                self._listeners.pop(event_name, None)
