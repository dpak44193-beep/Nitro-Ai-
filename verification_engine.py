from __future__ import annotations

import time
from typing import Any, Dict

from action_schema import ActionTool


class VerificationEngine:
    """Poll the real observer until an action's expected state is verified."""

    def __init__(self, observer):
        self.observer = observer

    def verify(self, action: ActionTool, before_screen=None) -> Dict[str, Any]:
        validation = action.validate()
        if not validation["valid"]:
            return {"status": "FAILURE", "reason": validation["reason"]}

        expected = action.expected_state.to_dict()
        if not expected:
            return {
                "status": "FAILURE",
                "reason": "expected_state_required",
                "action_id": action.action_id,
            }

        start_time = time.time()
        last_result: Dict[str, Any] = {}
        while time.time() - start_time < action.timeout:
            last_result = self.observer.verify(
                expected=expected,
                before_screen=before_screen,
                wait=0.0,
            )
            if last_result.get("status") == "VERIFIED":
                return {
                    "status": "VERIFIED",
                    "action_id": action.action_id,
                    "expected_state": expected,
                    "observation": last_result,
                    "verification_time": round(time.time() - start_time, 3),
                }
            time.sleep(0.25)

        return {
            "status": "FAILURE",
            "reason": "verification_timeout",
            "action_id": action.action_id,
            "expected_state": expected,
            "timeout": action.timeout,
            "last_observation": last_result,
        }
