from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExpectedState:
    """State that must be observed after an action."""

    window: Optional[str] = None
    text: Optional[str] = None
    screen_changed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.window:
            result["window"] = self.window
        if self.text:
            result["text"] = self.text
        if self.screen_changed:
            result["screen_changed"] = True
        return result


@dataclass
class RetryPolicy:
    max_retries: int = 0
    retry_delay: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
        }


@dataclass
class ActionTool:
    action_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_state: ExpectedState = field(default_factory=ExpectedState)
    timeout: float = 10.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    risk_level: str = "low"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> Dict[str, Any]:
        valid_risk_levels = {"low", "medium", "high", "critical"}
        if not self.action_id:
            return {"valid": False, "reason": "action_id is required"}
        if self.timeout <= 0:
            return {"valid": False, "reason": "timeout must be greater than zero"}
        if self.risk_level not in valid_risk_levels:
            return {"valid": False, "reason": f"invalid risk_level: {self.risk_level}"}
        if self.retry_policy.max_retries < 0:
            return {"valid": False, "reason": "max_retries cannot be negative"}
        if self.retry_policy.retry_delay < 0:
            return {"valid": False, "reason": "retry_delay cannot be negative"}
        return {"valid": True, "reason": "valid"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "parameters": self.parameters,
            "expected_state": self.expected_state.to_dict(),
            "timeout": self.timeout,
            "retry_policy": self.retry_policy.to_dict(),
            "risk_level": self.risk_level,
            "metadata": self.metadata,
        }


class ActionBuilder:
    """Helpers for creating actions with explicit verification contracts."""

    @staticmethod
    def open_app(app: str, expected_window: str, timeout: float = 10.0,
                 retries: int = 2, risk_level: str = "low") -> ActionTool:
        return ActionTool(
            action_id="OPEN_APP",
            parameters={"app": app},
            expected_state=ExpectedState(window=expected_window),
            timeout=timeout,
            retry_policy=RetryPolicy(max_retries=retries),
            risk_level=risk_level,
        )

    @staticmethod
    def type_text(text: str, expected_text: str, timeout: float = 5.0,
                  retries: int = 1, risk_level: str = "low") -> ActionTool:
        return ActionTool(
            action_id="TYPE_TEXT",
            parameters={"text": text},
            expected_state=ExpectedState(text=expected_text),
            timeout=timeout,
            retry_policy=RetryPolicy(max_retries=retries),
            risk_level=risk_level,
        )

    @staticmethod
    def click(x: int, y: int, expected_text: Optional[str] = None,
              expected_window: Optional[str] = None, timeout: float = 5.0,
              retries: int = 2, risk_level: str = "low") -> ActionTool:
        return ActionTool(
            action_id="CLICK",
            parameters={"x": x, "y": y},
            expected_state=ExpectedState(window=expected_window, text=expected_text),
            timeout=timeout,
            retry_policy=RetryPolicy(max_retries=retries),
            risk_level=risk_level,
        )

    @staticmethod
    def open_url(url: str, expected_text: Optional[str] = None,
                 expected_window: Optional[str] = None, timeout: float = 15.0,
                 retries: int = 2, risk_level: str = "low") -> ActionTool:
        return ActionTool(
            action_id="OPEN_URL",
            parameters={"url": url},
            expected_state=ExpectedState(window=expected_window, text=expected_text),
            timeout=timeout,
            retry_policy=RetryPolicy(max_retries=retries),
            risk_level=risk_level,
        )
