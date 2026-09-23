from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List


class RecoveryEngine:
    """Diagnose failed desktop actions, try bounded strategies, and re-verify."""

    def __init__(self, desktop_agent):
        self.desktop_agent = desktop_agent
        self.recovery_history: List[Dict[str, Any]] = []
        self.max_attempts = 3

    def recover(
        self,
        action: str,
        input_data: Dict[str, Any],
        expected: Dict[str, Any],
        failure_reason: str,
        execution_id: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        context = {
            "execution_id": execution_id,
            "action": action,
            "input_data": input_data,
            "expected": expected,
            "failure_reason": failure_reason,
            "started_at": datetime.now().isoformat(),
            "attempts": [],
        }
        diagnosis = self._diagnose(action, input_data, failure_reason)
        context["diagnosis"] = diagnosis
        strategies = diagnosis.get("strategies", [])[: self.max_attempts]

        for attempt_number, strategy in enumerate(strategies, start=1):
            attempt = {
                "attempt": attempt_number,
                "strategy": strategy,
                "started_at": datetime.now().isoformat(),
            }
            try:
                recovery_result = self._execute_strategy(
                    strategy, action, input_data, dry_run
                )
                attempt["recovery_result"] = recovery_result
                if not recovery_result.get("success", False):
                    attempt["status"] = "RECOVERY_ACTION_FAILED"
                    context["attempts"].append(attempt)
                    continue

                verification = self._verify_recovery(expected)
                attempt["verification"] = verification
                if verification.get("verified", False):
                    attempt["status"] = "RECOVERED"
                    context["attempts"].append(attempt)
                    context.update({
                        "status": "RECOVERED",
                        "recovered": True,
                        "completed_at": datetime.now().isoformat(),
                    })
                    self.recovery_history.append(context)
                    return {
                        "status": "RECOVERED",
                        "recovered": True,
                        "execution_id": execution_id,
                        "strategy": strategy,
                        "attempt": attempt_number,
                        "diagnosis": diagnosis,
                        "verification": verification,
                        "message": f"Action recovered using: {strategy}",
                    }
                attempt["status"] = "VERIFICATION_FAILED"
            except Exception as exc:
                attempt["status"] = "EXCEPTION"
                attempt["error"] = str(exc)
            context["attempts"].append(attempt)

        return self._final_failure(
            context,
            self._user_friendly_failure(action, failure_reason, diagnosis),
        )

    def _diagnose(self, action: str, input_data: Dict[str, Any], failure_reason: str) -> Dict[str, Any]:
        strategies = {
            "open_app": [
                "activate_existing_window",
                "retry_application_launch",
                "refresh_screen_and_retry",
            ],
            "click_at": [
                "retry_click",
                "refresh_screen_and_retry",
                "alternate_click",
            ],
            "type_text": [
                "retry_type",
                "refocus_and_type",
                "clipboard_type",
            ],
            "search_web": ["retry_web_action", "refresh_screen_and_retry"],
            "open_url": ["retry_web_action", "refresh_screen_and_retry"],
        }
        failure_types = {
            "open_app": "APPLICATION_OPEN_FAILED",
            "click_at": "CLICK_TARGET_NOT_CONFIRMED",
            "type_text": "TEXT_ENTRY_NOT_CONFIRMED",
            "search_web": "WEB_ACTION_FAILED",
            "open_url": "WEB_ACTION_FAILED",
        }
        return {
            "failure_type": failure_types.get(action, "UNKNOWN"),
            "target": input_data.get("app", ""),
            "reason": failure_reason,
            "strategies": strategies.get(
                action, ["retry_original_action", "refresh_screen_and_retry"]
            ),
        }

    def _execute_strategy(self, strategy: str, action: str, input_data: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        if strategy == "activate_existing_window":
            app = str(input_data.get("app", "")).strip()
            return {
                "success": bool(app) and self._activate_existing_window(app),
                "strategy": strategy,
                "app": app,
            }

        if strategy == "retry_application_launch":
            app = input_data.get("app", "")
            result = self.desktop_agent.open_application(app, dry_run=dry_run)
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        if strategy == "refresh_screen_and_retry":
            refresh = self.desktop_agent.refresh_screen_context()
            if refresh.get("status") not in {"completed", "success"}:
                return {"success": False, "strategy": strategy, "reason": "screen_refresh_failed", "refresh": refresh}
            time.sleep(0.5)
            result = self._retry_original_action(action, input_data, dry_run)
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        if strategy == "retry_click":
            result = self.desktop_agent.click_at(
                int(input_data.get("x")), int(input_data.get("y")),
                clicks=int(input_data.get("clicks", 1)), dry_run=dry_run,
            )
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        if strategy == "alternate_click":
            result = self.desktop_agent.click_at(
                int(input_data.get("x")) + 2, int(input_data.get("y")) + 2,
                clicks=1, dry_run=dry_run,
            )
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        if strategy == "retry_type":
            result = self.desktop_agent.type_text(input_data.get("text", ""), dry_run=dry_run)
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        if strategy == "refocus_and_type":
            if input_data.get("x") is not None and input_data.get("y") is not None:
                focused = self.desktop_agent.click_at(
                    int(input_data["x"]), int(input_data["y"]), dry_run=dry_run
                )
                if not self._action_succeeded(focused):
                    return {"success": False, "strategy": strategy, "reason": "refocus_click_failed"}
            result = self.desktop_agent.type_text(input_data.get("text", ""), dry_run=dry_run)
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        if strategy == "clipboard_type":
            try:
                import pyautogui
                import pyperclip
                if not dry_run:
                    pyperclip.copy(input_data.get("text", ""))
                    pyautogui.hotkey("ctrl", "v")
                return {"success": True, "strategy": strategy, "method": "clipboard"}
            except Exception as exc:
                return {"success": False, "strategy": strategy, "reason": str(exc)}

        if strategy in {"retry_web_action", "retry_original_action"}:
            result = self._retry_original_action(action, input_data, dry_run)
            return {"success": self._action_succeeded(result), "strategy": strategy, "result": result}

        return {"success": False, "reason": f"unknown_recovery_strategy:{strategy}"}

    @staticmethod
    def _action_succeeded(result: Dict[str, Any]) -> bool:
        return result.get("status") in {"completed", "success", "dry_run"}

    def _activate_existing_window(self, app_name: str) -> bool:
        try:
            import pygetwindow
            windows = [
                window for window in pygetwindow.getAllWindows()
                if app_name.lower() in window.title.lower()
            ]
            if not windows:
                return False
            window = windows[-1]
            try:
                if window.isMinimized:
                    window.restore()
            except Exception:
                pass
            try:
                window.activate()
            except Exception:
                pass
            time.sleep(0.5)
            return True
        except Exception:
            return False

    def _retry_original_action(self, action: str, input_data: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        methods = {
            "open_app": lambda: self.desktop_agent.open_application(input_data.get("app", ""), dry_run=dry_run),
            "click_at": lambda: self.desktop_agent.click_at(int(input_data.get("x")), int(input_data.get("y")), int(input_data.get("clicks", 1)), dry_run=dry_run),
            "type_text": lambda: self.desktop_agent.type_text(input_data.get("text", ""), dry_run=dry_run),
            "press_key": lambda: self.desktop_agent.press_key(input_data.get("key", ""), dry_run=dry_run),
            "search_web": lambda: self.desktop_agent.search_web(input_data.get("query", ""), dry_run=dry_run),
            "open_url": lambda: self.desktop_agent.open_url(input_data.get("url", ""), dry_run=dry_run),
        }
        try:
            return methods.get(action, lambda: {"status": "failed", "error": f"unsupported_recovery_action:{action}"})()
        except (TypeError, ValueError) as exc:
            return {"status": "failed", "error": str(exc)}

    def _verify_recovery(self, expected: Dict[str, Any]) -> Dict[str, Any]:
        try:
            verification = self.desktop_agent.observer.verify(expected=expected, before_screen=None, wait=1.0)
            return {
                "verified": verification.get("status") == "VERIFIED",
                "status": verification.get("status", "FAILURE"),
                "reason": verification.get("reason", ""),
                "details": verification,
            }
        except Exception as exc:
            return {"verified": False, "status": "FAILURE", "reason": str(exc)}

    def _user_friendly_failure(self, action: str, failure_reason: str, diagnosis: Dict[str, Any]) -> str:
        messages = {
            "APPLICATION_OPEN_FAILED": f"Task complete panna mudila. {diagnosis.get('target', 'Application')} open aagala.",
            "CLICK_TARGET_NOT_CONFIRMED": "Task complete panna mudila. Button/action confirm panna mudila.",
            "TEXT_ENTRY_NOT_CONFIRMED": "Task complete panna mudila. Text target field-la enter aagala.",
            "WEB_ACTION_FAILED": "Task complete panna mudila. Browser page load aagala.",
        }
        return messages.get(diagnosis.get("failure_type"), f"Task complete panna mudila. Reason: {failure_reason}")

    def _final_failure(self, context: Dict[str, Any], message: str) -> Dict[str, Any]:
        context.update({
            "status": "RECOVERY_FAILED",
            "recovered": False,
            "message": message,
            "completed_at": datetime.now().isoformat(),
        })
        self.recovery_history.append(context)
        return {
            "status": "RECOVERY_FAILED",
            "recovered": False,
            "execution_id": context["execution_id"],
            "message": message,
            "diagnosis": context.get("diagnosis", {}),
            "attempts": context.get("attempts", []),
        }
