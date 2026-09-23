"""Shared runtime context for correlated tasks and live HUD state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RuntimeContext:
    session_id: str
    task_id: Optional[str] = None
    current_app: Optional[str] = None
    active_window: Optional[str] = None
    current_url: Optional[str] = None
    current_page: Optional[str] = None
    current_intent: Optional[str] = None
    current_action: Optional[str] = None
    previous_action: Optional[str] = None
    expected_state: Dict[str, Any] = field(default_factory=dict)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    interruption_state: str = "none"
    agent_state: str = "IDLE"

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)

    def add_observation(self, observation: Dict[str, Any]) -> None:
        self.observations.append(observation)
        self.observations = self.observations[-20:]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
