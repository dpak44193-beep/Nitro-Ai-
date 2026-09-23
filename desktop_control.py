"""Priority 7: policy-controlled desktop and system actions."""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyautogui

try:
    import pygetwindow
except ImportError:  # pragma: no cover
    pygetwindow = None

try:
    import pyperclip
except ImportError:  # pragma: no cover
    pyperclip = None


@dataclass
class DesktopAction:
    action_id: str
    category: str
    operation: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_state: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 10.0
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {"max_retries": 1})
    risk_level: str = "low"
    requested_by: str = "local_user"
    task_id: Optional[str] = None
    correlation_id: Optional[str] = None


class DesktopPolicy:
    """Allowlist and risk policy for desktop control."""

    ALLOWED_CATEGORIES = {
        "windows", "apps", "files", "keyboard", "mouse", "clipboard",
        "browser", "process", "network", "terminal",
    }
    HIGH_RISK_OPERATIONS = {("files", "delete"), ("files", "overwrite"), ("process", "terminate"), ("windows", "close"), ("apps", "close")}
    CRITICAL_OPERATIONS = {("network", "disable"), ("system", "shutdown"), ("system", "restart")}
    TERMINAL_ALLOWLIST = {
        "whoami": ["whoami"],
        "hostname": ["hostname"],
        "ver": ["cmd.exe", "/c", "ver"],
        "ipconfig": ["ipconfig"],
        "ipconfig_all": ["ipconfig", "/all"],
        "tasklist": ["tasklist"],
        "systeminfo": ["systeminfo"],
    }

    def __init__(self, allow_medium: bool = True, allow_high: bool = False, allow_critical: bool = False):
        self.allow_medium = allow_medium
        self.allow_high = allow_high
        self.allow_critical = allow_critical

    def evaluate(self, action: DesktopAction, has_explicit_permission: bool = False) -> Dict[str, Any]:
        category, operation = action.category.lower(), action.operation.lower()
        if category not in self.ALLOWED_CATEGORIES:
            return {"allowed": False, "reason": f"category_not_allowed: {category}"}
        if (category, operation) in self.CRITICAL_OPERATIONS and (not self.allow_critical or not has_explicit_permission):
            return {"allowed": False, "reason": "critical_permission_required"}
        if (category, operation) in self.HIGH_RISK_OPERATIONS and (not self.allow_high or not has_explicit_permission):
            return {"allowed": False, "reason": "high_risk_permission_required"}
        if action.risk_level == "medium" and not self.allow_medium:
            return {"allowed": False, "reason": "medium_risk_actions_disabled"}
        if action.risk_level == "high" and (not self.allow_high or not has_explicit_permission):
            return {"allowed": False, "reason": "high_risk_permission_required"}
        if action.risk_level == "critical" and (not self.allow_critical or not has_explicit_permission):
            return {"allowed": False, "reason": "critical_permission_required"}
        return {"allowed": True, "reason": "policy_allowed"}

    @classmethod
    def validate_terminal_command(cls, command_name: str, parameters: Optional[List[str]] = None) -> Optional[List[str]]:
        command = cls.TERMINAL_ALLOWLIST.get(command_name.lower().strip())
        return list(command) if command is not None and not parameters else None


class DesktopAudit:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def log(self, action: DesktopAction, phase: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({
            "event_id": str(uuid.uuid4())[:16],
            "timestamp": datetime.now().isoformat(),
            "action_id": action.action_id,
            "task_id": action.task_id,
            "correlation_id": action.correlation_id,
            "category": action.category,
            "operation": action.operation,
            "risk_level": action.risk_level,
            "phase": phase,
            "status": status,
            "details": details or {},
        })

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.events[-limit:]


class DesktopControl:
    """Execute allowlisted desktop operations without arbitrary shell access."""

    def __init__(self, desktop_agent=None, policy: Optional[DesktopPolicy] = None):
        self.desktop_agent = desktop_agent
        self.policy = policy or DesktopPolicy()
        self.audit = DesktopAudit()
        home = Path.home().resolve()
        self.safe_file_roots = [home / "Desktop", home / "Documents", home / "Downloads"]

    def execute(self, action: DesktopAction, has_explicit_permission: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        self.audit.log(action, "POLICY", "checking")
        policy = self.policy.evaluate(action, has_explicit_permission)
        if not policy["allowed"]:
            self.audit.log(action, "POLICY", "denied", policy)
            return {"status": "denied", "action_id": action.action_id, "reason": policy["reason"]}
        if dry_run:
            self.audit.log(action, "EXECUTION", "dry_run")
            return {"status": "dry_run", "action_id": action.action_id, "category": action.category, "operation": action.operation, "parameters": action.parameters}
        self.audit.log(action, "EXECUTION", "started")
        try:
            result = self._dispatch(action)
            self.audit.log(action, "EXECUTION", result.get("status", "failed"), result)
            return result
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
            self.audit.log(action, "EXECUTION", "exception", result)
            return result

    def _dispatch(self, action: DesktopAction) -> Dict[str, Any]:
        handlers = {
            "windows": self._windows, "apps": self._apps, "files": self._files,
            "keyboard": self._keyboard, "mouse": self._mouse, "clipboard": self._clipboard,
            "browser": self._browser, "process": self._process, "network": self._network,
            "terminal": self._terminal,
        }
        handler = handlers.get(action.category.lower())
        return handler(action) if handler else {"status": "failed", "error": f"unsupported_category:{action.category}"}

    def _windows(self, action: DesktopAction) -> Dict[str, Any]:
        if pygetwindow is None:
            return {"status": "failed", "error": "pygetwindow_not_installed"}
        title = str(action.parameters.get("title", "")).strip()
        windows = [window for window in pygetwindow.getAllWindows() if title.lower() in window.title.lower()]
        if not windows:
            return {"status": "failed", "error": f"window_not_found:{title}"}
        window = windows[-1]
        operation = action.operation.lower()
        if operation == "activate":
            window.restore(); window.activate()
        elif operation == "minimize":
            window.minimize()
        elif operation == "maximize":
            window.maximize()
        elif operation == "close":
            window.close()
        else:
            return {"status": "failed", "error": f"unsupported_window_operation:{operation}"}
        time.sleep(0.3)
        return {"status": "completed", "window": window.title, "operation": operation}

    def _apps(self, action: DesktopAction) -> Dict[str, Any]:
        if self.desktop_agent is None:
            return {"status": "failed", "error": "desktop_agent_not_connected"}
        app = str(action.parameters.get("app", "")).strip()
        if action.operation.lower() == "open":
            return self.desktop_agent.open_application(app)
        if action.operation.lower() == "activate":
            return self._windows(DesktopAction(action.action_id, "windows", "activate", {"title": app}, risk_level=action.risk_level))
        if action.operation.lower() == "close":
            return self._windows(DesktopAction(action.action_id, "windows", "close", {"title": app}, risk_level=action.risk_level))
        return {"status": "failed", "error": f"unsupported_app_operation:{action.operation}"}

    def _resolve_safe_path(self, value: str) -> Path:
        candidate = Path(value).expanduser().resolve()
        for root in self.safe_file_roots:
            try:
                candidate.relative_to(root.resolve())
                return candidate
            except ValueError:
                continue
        raise PermissionError("file_path_outside_allowed_user_directories")

    def _files(self, action: DesktopAction) -> Dict[str, Any]:
        path_value = action.parameters.get("path")
        if not path_value:
            return {"status": "failed", "error": "file_path_required"}
        path = self._resolve_safe_path(str(path_value))
        operation = action.operation.lower()
        if operation == "list":
            if not path.is_dir(): return {"status": "failed", "error": "directory_not_found"}
            return {"status": "completed", "path": str(path), "entries": [{"name": item.name, "type": "directory" if item.is_dir() else "file"} for item in path.iterdir()]}
        if operation == "create":
            path.parent.mkdir(parents=True, exist_ok=True); path.touch(exist_ok=True); return {"status": "completed", "path": str(path)}
        if operation == "read":
            if not path.is_file(): return {"status": "failed", "error": "file_not_found"}
            return {"status": "completed", "path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")}
        if operation in {"write", "overwrite"}:
            path.parent.mkdir(parents=True, exist_ok=True); content = str(action.parameters.get("content", "")); path.write_text(content, encoding="utf-8"); return {"status": "completed", "path": str(path), "bytes": len(content.encode("utf-8"))}
        if operation == "rename":
            new_name = str(action.parameters.get("new_name", "")).strip()
            if not new_name: return {"status": "failed", "error": "new_name_required"}
            target = self._resolve_safe_path(str(path.parent / new_name)); path.rename(target); return {"status": "completed", "old_path": str(path), "new_path": str(target)}
        if operation == "delete":
            path.unlink(); return {"status": "completed", "path": str(path)}
        return {"status": "failed", "error": f"unsupported_file_operation:{operation}"}

    def _keyboard(self, action: DesktopAction) -> Dict[str, Any]:
        operation = action.operation.lower()
        if operation == "press": pyautogui.press(str(action.parameters["key"])); return {"status": "completed", "key": action.parameters["key"]}
        if operation == "hotkey":
            keys = action.parameters.get("keys", []); pyautogui.hotkey(*keys); return {"status": "completed", "keys": keys}
        if operation == "type":
            text = str(action.parameters.get("text", ""))
            if any(ord(char) > 127 for char in text) and pyperclip: pyperclip.copy(text); pyautogui.hotkey("ctrl", "v")
            else: pyautogui.write(text)
            return {"status": "completed", "typed_length": len(text)}
        return {"status": "failed", "error": f"unsupported_keyboard_operation:{operation}"}

    def _mouse(self, action: DesktopAction) -> Dict[str, Any]:
        operation = action.operation.lower()
        if operation == "move": pyautogui.moveTo(int(action.parameters["x"]), int(action.parameters["y"])); return {"status": "completed"}
        if operation == "click":
            pyautogui.click(x=int(action.parameters["x"]), y=int(action.parameters["y"]), clicks=int(action.parameters.get("clicks", 1))); return {"status": "completed"}
        if operation == "scroll": pyautogui.scroll(int(action.parameters.get("amount", 0))); return {"status": "completed"}
        return {"status": "failed", "error": f"unsupported_mouse_operation:{operation}"}

    def _clipboard(self, action: DesktopAction) -> Dict[str, Any]:
        if pyperclip is None: return {"status": "failed", "error": "pyperclip_not_installed"}
        if action.operation.lower() == "read": return {"status": "completed", "content": pyperclip.paste()}
        if action.operation.lower() == "write":
            text = str(action.parameters.get("text", "")); pyperclip.copy(text); return {"status": "completed", "length": len(text)}
        return {"status": "failed", "error": "unsupported_clipboard_operation"}

    def _process(self, action: DesktopAction) -> Dict[str, Any]:
        if action.operation.lower() == "list": command = ["tasklist"]
        elif action.operation.lower() == "terminate":
            pid = action.parameters.get("pid")
            if pid is None: return {"status": "failed", "error": "pid_required"}
            command = ["taskkill", "/PID", str(int(pid))]
        else: return {"status": "failed", "error": "unsupported_process_operation"}
        completed = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=action.timeout)
        return {"status": "completed" if completed.returncode == 0 else "failed", "stdout": completed.stdout, "stderr": completed.stderr}

    def _network(self, action: DesktopAction) -> Dict[str, Any]:
        commands = {"status": ["ipconfig"], "details": ["ipconfig", "/all"], "hostname": ["hostname"], "identity": ["whoami"]}
        command = commands.get(action.operation.lower())
        if command is None: return {"status": "denied", "error": "network_operation_not_allowed"}
        completed = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=action.timeout)
        return {"status": "completed" if completed.returncode == 0 else "failed", "stdout": completed.stdout, "stderr": completed.stderr}

    def _terminal(self, action: DesktopAction) -> Dict[str, Any]:
        name = str(action.parameters.get("command", "")).strip().lower()
        command = self.policy.validate_terminal_command(name, action.parameters.get("arguments", []))
        if command is None: return {"status": "denied", "error": "terminal_command_not_allowlisted", "command": name}
        completed = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=action.timeout)
        return {"status": "completed" if completed.returncode == 0 else "failed", "command": name, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}

    def _browser(self, action: DesktopAction) -> Dict[str, Any]:
        browser = getattr(self.desktop_agent, "browser", None)
        if browser is None: return {"status": "failed", "error": "browser_intelligence_not_connected"}
        operations = {
            "navigate": lambda: browser.navigate(action.parameters["url"]),
            "click_button": lambda: browser.click_button(action.parameters["name"]),
            "click_link": lambda: browser.click_link(action.parameters["name"]),
            "fill": lambda: browser.fill_input(action.parameters["target"], action.parameters["value"]),
            "search": lambda: browser.search_google(action.parameters["query"]),
            "state": browser.get_page_state,
        }
        operation = operations.get(action.operation.lower())
        return operation() if operation else {"status": "failed", "error": f"unsupported_browser_operation:{action.operation}"}


def create_desktop_action(category: str, operation: str, parameters: Optional[Dict[str, Any]] = None, expected_state: Optional[Dict[str, Any]] = None, risk_level: str = "low", task_id: Optional[str] = None, correlation_id: Optional[str] = None) -> DesktopAction:
    return DesktopAction(str(uuid.uuid4())[:16], category, operation, parameters or {}, expected_state or {}, risk_level=risk_level, task_id=task_id, correlation_id=correlation_id)
