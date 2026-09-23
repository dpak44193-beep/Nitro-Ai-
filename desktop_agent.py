"""Local instruction-driven desktop agent.

This module provides a simple, local, OpenAI-like workflow for a desktop assistant:
- accepts natural-language instructions,
- parses them into simple actions,
- optionally calls a local Ollama endpoint when available,
- and performs screen-aware operations such as screenshot, click, type, and open app.

The goal is not to replace a full autonomous browser/desktop framework; it is a
practical starter for building a local, instruction-driven automation assistant.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import time
import threading
import webbrowser
import queue
from datetime import datetime
from typing import Any, Dict, List, Optional

import pyautogui
from browser_intelligence import BrowserIntelligence
from real_observer import RealObserver
from tanglish_nlp import IntentActionMapper, TanglishNormalizer
from verification_engine import VerificationEngine

try:
    import pyttsx3  # type: ignore
except Exception:  # pragma: no cover
    pyttsx3 = None

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import pyperclip  # type: ignore
except Exception:  # pragma: no cover
    pyperclip = None

try:
    import pygetwindow  # type: ignore
except Exception:  # pragma: no cover
    pygetwindow = None

try:
    import ollama  # type: ignore
except Exception:  # pragma: no cover
    ollama = None


class SentinelGuard:
    """Guard sensitive local actions behind an admin/sentinel approval gate."""

    RESTRICTED_ACTIONS = {
        "shutdown",
        "restart",
        "delete_system_file",
        "kill_process",
        "install_software",
        "modify_registry",
        "network_disable",
        "browser_clear_data",
        "drop_database",
    }

    def __init__(self, admin_mode: bool = False):
        self.admin_mode = admin_mode

    def allow_action(self, action_name: str) -> bool:
        key = action_name.lower().strip()
        if key in self.RESTRICTED_ACTIONS and not self.admin_mode:
            return False
        return True


class VoiceInput:
    """Optional microphone-based voice capture for local instructions."""

    def __init__(self):
        self.recognizer = None
        self.microphone = None
        self.speaker = None
        self._ambient_calibrated = False
        self._stop_event = threading.Event()
        self._listener_thread = None

        try:
            import speech_recognition as sr  # type: ignore
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
        except Exception:  # pragma: no cover
            self.recognizer = None
            self.microphone = None

        if pyttsx3 is not None:
            try:
                self.speaker = pyttsx3.init()
                self.speaker.setProperty("rate", 180)
                self.speaker.setProperty("voice", self.speaker.getProperty("voices")[0].id)
            except Exception:  # pragma: no cover
                self.speaker = None

    def speak(self, text: str) -> Dict[str, Any]:
        if self.speaker is None:
            return {"status": "unavailable", "message": "text-to-speech is not configured on this machine"}

        try:
            self.speaker.say(text)
            self.speaker.runAndWait()
            return {"status": "completed", "text": text}
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "error": str(exc)}

    def listen_for_command(self, timeout: int = 10) -> Dict[str, Any]:
        if self.recognizer is None or self.microphone is None:
            return {"status": "unavailable", "message": "voice capture is not configured on this machine"}

        try:
            with self.microphone as source:
                if not self._ambient_calibrated:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    self._ambient_calibrated = True
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=12)
            text = self.recognizer.recognize_google(audio)
            return {"status": "completed", "text": text}
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "error": str(exc)}

    def start_live_listening(self, command_handler, status_handler=None) -> Dict[str, Any]:
        """Continuously recognize short phrases and dispatch each as an instruction."""
        if self.recognizer is None or self.microphone is None:
            return {"status": "unavailable", "message": "voice capture is not configured on this machine"}
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return {"status": "already_running"}

        self._stop_event.clear()

        def listen_loop():
            try:
                while not self._stop_event.is_set():
                    result = self.listen_for_command(timeout=1)
                    if result.get("status") != "completed":
                        continue
                    text = result.get("text", "").strip()
                    if not text:
                        continue
                    if status_handler is not None:
                        status_handler(f"Heard: {text}")
                    try:
                        command_result = command_handler(text)
                        if status_handler is not None:
                            status_handler(f"Voice result: {command_result.get('status', 'unknown')}")
                    except Exception as exc:  # pragma: no cover
                        if status_handler is not None:
                            status_handler(f"Voice command error: {exc}")
            finally:
                self._listener_thread = None

        self._listener_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listener_thread.start()
        return {"status": "started"}

    def stop_live_listening(self) -> Dict[str, Any]:
        self._stop_event.set()
        return {"status": "stopping"}


class SimpleOverlay:
    """Lightweight local overlay window for the agent status and quick actions."""

    def __init__(self, title: str = "Local Agent Overlay"):
        self.title = title
        self._root = None
        self._thread = None
        self._status_var = None
        self._entry = None
        self._command_handler = None
        self._voice_handler = None
        self._refresh_handler = None
        self._status_queue = queue.Queue()
        self._busy = False
        self._busy_lock = threading.Lock()

    def set_callbacks(self, command_handler=None, voice_handler=None, refresh_handler=None):
        self._command_handler = command_handler
        self._voice_handler = voice_handler
        self._refresh_handler = refresh_handler

    def _set_status(self, message: str):
        if self._root is not None and self._status_var is not None:
            if threading.current_thread() is self._thread:
                self._status_var.set(message)
            else:
                self._status_queue.put(message)

    def _poll_status(self):
        if self._root is None or not self._root.winfo_exists():
            return
        try:
            while True:
                self._status_var.set(self._status_queue.get_nowait())
        except queue.Empty:
            pass
        self._root.after(100, self._poll_status)

    def _run_background(self, status: str, task, on_success=None):
        with self._busy_lock:
            if self._busy:
                self._set_status("Another command is still running")
                return False
            self._busy = True

        self._set_status(status)

        def worker():
            try:
                result = task()
                if on_success is not None:
                    on_success(result)
            except Exception as exc:  # pragma: no cover
                self._set_status(f"Error: {exc}")
            finally:
                with self._busy_lock:
                    self._busy = False

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _refresh_from_overlay(self):
        if self._refresh_handler is None:
            self._set_status("Refresh is unavailable")
            return

        def completed(result):
            status = result.get("status", "unknown")
            self._set_status(f"Refresh: {status}")

        self._run_background("Refreshing screen...", self._refresh_handler, completed)

    def _listen_from_overlay(self):
        if self._voice_handler is None:
            self._set_status("Voice input is unavailable")
            return

        def listen_task():
            try:
                result = self._voice_handler("listen", timeout=10)
                if result.get("status") != "completed":
                    self._set_status(result.get("message", result.get("error", "Voice failed")))
                    return result

                text = result.get("text", "").strip()
                self._root.after(0, self._set_entry, text)
                if not text or self._command_handler is None:
                    self._set_status("No voice command detected")
                    return result
                self._set_status("Running voice command...")
                command_result = self._command_handler(text)
                self._set_status(f"Voice result: {command_result.get('status', 'unknown')}")
                return result
            finally:
                self._set_status("Voice processing finished")

        self._run_background("Listening...", listen_task)

    def _set_entry(self, text: str):
        if self._entry is not None:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, text)

    def _start_live_voice_from_overlay(self):
        if self._voice_handler is None or self._command_handler is None:
            self._set_status("Voice input is unavailable")
            return
        result = self._voice_handler("start_live", self._command_handler, self._set_status)
        self._set_status(f"Live voice: {result.get('status', 'unknown')}")

    def _stop_live_voice_from_overlay(self):
        if self._voice_handler is None:
            return
        result = self._voice_handler("stop_live")
        self._set_status(f"Live voice: {result.get('status', 'unknown')}")

    def _run_from_overlay(self):
        if self._entry is None:
            return

        text = self._entry.get().strip()
        if not text:
            self._set_status("Enter a command first")
            return

        if self._command_handler is not None:
            def run_command():
                return self._command_handler(text)

            self._run_background(
                "Running command...",
                run_command,
                lambda result: self._set_status(f"Result: {result.get('status', 'unknown')}"),
            )
        else:
            self._set_status("No command handler configured")

    def start(self, command_handler=None, voice_handler=None):
        if tk is None:
            return {"status": "unavailable", "message": "tkinter is not available in this environment"}

        if command_handler is not None:
            self._command_handler = command_handler
        if voice_handler is not None:
            self._voice_handler = voice_handler

        def run():
            root = tk.Tk()
            self._root = root
            root.title(self.title)
            root.attributes("-topmost", True)
            root.geometry("420x220")
            root.configure(background="#111827")

            title_label = tk.Label(root, text="Local Agent Command Panel", fg="white", bg="#111827", font=("Segoe UI", 12, "bold"))
            title_label.pack(pady=(10, 4))

            self._status_var = tk.StringVar(value="Agent ready")
            status_label = tk.Label(root, textvariable=self._status_var, fg="#d1fae5", bg="#111827", font=("Segoe UI", 10))
            status_label.pack(pady=(0, 8))

            self._entry = tk.Entry(root, width=42, font=("Segoe UI", 11))
            self._entry.insert(0, "take screenshot")
            self._entry.pack(pady=(0, 8))

            button_row = tk.Frame(root, bg="#111827")
            button_row.pack()

            run_btn = tk.Button(button_row, text="Run", fg="#111827", bg="#22c55e", command=self._run_from_overlay, width=12)
            run_btn.pack(side=tk.LEFT, padx=6)

            refresh_btn = tk.Button(button_row, text="Refresh", fg="#111827", bg="#cbd5e1", command=self._refresh_from_overlay, width=12)
            refresh_btn.pack(side=tk.LEFT, padx=6)

            listen_btn = tk.Button(button_row, text="Listen", fg="#111827", bg="#60a5fa", command=self._listen_from_overlay, width=12)
            listen_btn.pack(side=tk.LEFT, padx=6)

            live_row = tk.Frame(root, bg="#111827")
            live_row.pack(pady=(10, 0))
            live_btn = tk.Button(live_row, text="Start live voice", fg="#111827", bg="#fbbf24", command=self._start_live_voice_from_overlay, width=16)
            live_btn.pack(side=tk.LEFT, padx=4)
            stop_btn = tk.Button(live_row, text="Stop", fg="white", bg="#ef4444", command=self._stop_live_voice_from_overlay, width=8)
            stop_btn.pack(side=tk.LEFT, padx=4)

            root.after(100, self._poll_status)
            root.mainloop()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return {"status": "started", "title": self.title}


class LocalInstructionAgent:
    """Instruction-driven desktop automation agent.

    Local laptop mode keeps the permission guard active while allowing a full local
    desktop workflow for this machine under local user consent.
    """

    def __init__(
        self,
        allow_desktop_control: bool = True,
        local_model: str = "local-desktop-agent",
        local_laptop_mode: bool = True,
        permission_guard: bool = True,
        admin_mode: bool = False,
    ):
        self.agent_id = "local_desktop_agent_001"
        self.access_token = "local-desktop-agent-token"
        self.allow_desktop_control = allow_desktop_control
        self.local_laptop_mode = local_laptop_mode
        self.permission_guard = permission_guard
        self.local_consent = True
        self.local_model = local_model
        self.tanglish_nlp = TanglishNormalizer(
            llm_client=self._call_local_llm,
            model=self.local_model,
        )
        self.guard = SentinelGuard(admin_mode=admin_mode)
        self.voice = VoiceInput()
        self.overlay = SimpleOverlay()
        self.execution_log: List[Dict[str, Any]] = []
        self.capture_dir = os.path.join(os.getcwd(), "captures")
        os.makedirs(self.capture_dir, exist_ok=True)
        self.observer = RealObserver(self.capture_dir)
        self.browser = BrowserIntelligence(browser_name="edge", headless=False, timeout=10000)
        self.verification_engine = VerificationEngine(self.observer)
        self.screen_access_active = False
        self.screen_context_path: Optional[str] = None
        self.screen_size: Optional[Dict[str, int]] = None
        self.initialize_desktop_access(consent=self.local_consent)

    def initialize_desktop_access(self, consent: bool = False) -> Dict[str, Any]:
        """Establish local screen access once the user has granted local consent."""
        if not consent or not self.local_laptop_mode or not self.permission_guard:
            self.screen_access_active = False
            return {"status": "blocked", "reason": "local laptop consent and permission guard are required"}

        try:
            self.allow_desktop_control = True
            self.screen_size = {
                "width": pyautogui.size().width,
                "height": pyautogui.size().height,
            }
            context_path = os.path.join(self.capture_dir, "current_screen_context.png")
            pyautogui.screenshot().save(context_path)
            self.screen_context_path = context_path
            self.screen_access_active = True
            self._log("initialize_desktop_access", "completed", {
                "screen_size": self.screen_size,
                "context_path": context_path,
            })
            return {
                "status": "completed",
                "screen_access_active": True,
                "screen_size": self.screen_size,
                "context_path": context_path,
            }
        except Exception as exc:  # pragma: no cover
            self.screen_access_active = False
            self._log("initialize_desktop_access", "failed", {"error": str(exc)})
            return {"status": "failed", "error": str(exc)}

    def refresh_screen_context(self) -> Dict[str, Any]:
        """Refresh the internal current-screen context without exposing it externally."""
        if not self.screen_access_active:
            return {"status": "blocked", "reason": "desktop screen access is not active"}

        try:
            context_path = os.path.join(self.capture_dir, "current_screen_context.png")
            pyautogui.screenshot().save(context_path)
            self.screen_context_path = context_path
            return {"status": "completed", "context_path": context_path}
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "error": str(exc)}

    def authorize(self, agent_id: Optional[str], access_token: Optional[str], consent: bool = True) -> bool:
        """Allow local laptop access while keeping the permission gate in place."""
        if not consent:
            return False
        if self.local_laptop_mode:
            self.allow_desktop_control = True
            return True
        if agent_id == self.agent_id and access_token == self.access_token:
            self.allow_desktop_control = True
            return True
        return False

    def _log(self, action: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "status": status,
            "details": details or {},
        })

    def get_status(self) -> Dict[str, Any]:
        return {
            "allow_desktop_control": self.allow_desktop_control,
            "screen_access_active": self.screen_access_active,
            "screen_size": self.screen_size,
            "screen_context_path": self.screen_context_path,
            "local_model": self.local_model,
            "voice_input_available": self.voice.recognizer is not None and self.voice.microphone is not None,
            "text_to_speech_available": self.voice.speaker is not None,
            "captures_dir": self.capture_dir,
            "browser_started": self.browser.started,
            "execution_count": len(self.execution_log),
        }

    def browser_start(self) -> Dict[str, Any]:
        return self.browser.start()

    def browser_navigate(self, url: str) -> Dict[str, Any]:
        return self.browser.navigate(url)

    def browser_state(self) -> Dict[str, Any]:
        return self.browser.get_page_state()

    def browser_snapshot(self) -> Dict[str, Any]:
        return self.browser.get_dom_snapshot()

    def browser_find_button(self, name: str) -> Dict[str, Any]:
        return self.browser.find_button(name)

    def browser_click_button(self, name: str) -> Dict[str, Any]:
        return self.browser.click_button(name)

    def browser_find_link(self, name: str) -> Dict[str, Any]:
        return self.browser.find_link(name)

    def browser_click_link(self, name: str) -> Dict[str, Any]:
        return self.browser.click_link(name)

    def browser_fill(self, target: str, value: str) -> Dict[str, Any]:
        return self.browser.fill_input(target, value)

    def browser_search(self, query: str) -> Dict[str, Any]:
        return self.browser.search_google(query)

    def browser_verify(self, expected: Dict[str, Any]) -> Dict[str, Any]:
        return self.browser.verify(expected)

    def speak(self, text: str) -> Dict[str, Any]:
        return self.voice.speak(text)

    def verify_action(
        self,
        action_result: Dict[str, Any],
        expected: Dict[str, Any],
        before_screen: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Verify an action against the real desktop state."""
        if action_result.get("status") not in {"completed", "success"}:
            return {
                "status": "FAILURE",
                "reason": "Action itself failed",
                "action_result": action_result,
            }

        verification = self.verification_engine.verify(
            action=self._verification_action(expected, timeout),
            before_screen=before_screen,
        )
        return {
            "status": verification["status"],
            "action": action_result,
            "verification": verification,
        }

    @staticmethod
    def _verification_action(expected: Dict[str, Any], timeout: float = 10.0):
        from action_schema import ActionTool, ExpectedState

        return ActionTool(
            action_id="VERIFY_ACTION",
            expected_state=ExpectedState(
                window=expected.get("window"),
                text=expected.get("text"),
                screen_changed=expected.get("screen_changed", False),
            ),
            timeout=timeout,
        )

    def execute_from_overlay(self, instruction: str) -> Dict[str, Any]:
        if not instruction or not instruction.strip():
            return {"status": "failed", "error": "empty instruction"}

        intent = self.tanglish_nlp.normalize(instruction)
        if intent.get("needs_clarification") or intent.get("intent") == "UNKNOWN":
            return {
                "status": "clarification_required",
                "message": intent.get("clarification_reason", "Command is ambiguous"),
                "intent": intent,
            }

        mapped = IntentActionMapper.to_action(intent)
        if not mapped.get("action"):
            return {
                "status": "clarification_required",
                "message": mapped.get("error", "Command cannot be mapped safely"),
                "intent": intent,
            }

        canonical_instruction = self._intent_to_instruction(mapped)
        result = self.execute_instruction(
            canonical_instruction,
            allow_desktop_control=True,
            consent=True,
        )
        result["intent"] = intent
        self.speak(f"Command finished with status {result.get('status', 'unknown')}")
        return result

    @staticmethod
    def _intent_to_instruction(mapped: Dict[str, Any]) -> str:
        action = mapped["action"]
        data = mapped.get("input_data", {})
        if action == "open_app":
            return f"open {data.get('app', '')}"
        if action == "search_web":
            return f"search web {data.get('query', '')}"
        if action == "type_text":
            return f"type {data.get('text', '')}"
        if action == "click_at":
            return f"click at {data.get('x')} {data.get('y')}"
        if action == "press_key":
            return f"press {data.get('key', '')}"
        if action == "wait":
            return f"wait {data.get('seconds', 1)}"
        if action == "take_screenshot":
            return "take screenshot"
        return ""

    def normalize_user_command(self, user_input: str) -> Dict[str, Any]:
        """Normalize English or Tanglish input without executing desktop actions."""
        intent = self.tanglish_nlp.normalize(user_input)
        return {
            "status": "completed",
            "raw_input": user_input,
            "intent": intent,
        }

    def execute_voice_command(self, timeout: int = 10) -> Dict[str, Any]:
        """Listen once and execute the recognized instruction through the guard."""
        voice_result = self.listen_voice_command(timeout=timeout)
        if voice_result.get("status") != "completed":
            return voice_result

        text = voice_result.get("text", "").strip()
        if not text:
            return {"status": "failed", "error": "no voice command detected"}

        result = self.execute_from_overlay(text)
        return {"status": result.get("status", "unknown"), "text": text, "result": result}

    def take_screenshot(self, filename: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        file_name = filename or f"screen_{int(time.time())}.png"
        path = os.path.join(self.capture_dir, file_name)

        if dry_run:
            return {"status": "dry_run", "path": path, "message": "Screenshot would be captured"}

        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        self._log("take_screenshot", "completed", {"path": path})
        return {"status": "completed", "path": path}

    def open_application(self, app_name: str, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        if dry_run:
            return {"status": "dry_run", "message": f"Would open {app_name}"}

        app_name = app_name.strip()
        aliases = {
            "edge": "msedge.exe",
            "microsoft edge": "msedge.exe",
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "vscode": "code.exe",
            "visual studio code": "code.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
        }
        launch_target = aliases.get(app_name.lower(), app_name)
        try:
            if os.name == "nt":
                if shutil.which(launch_target):
                    subprocess.Popen([launch_target], shell=False)
                else:
                    subprocess.Popen(["cmd.exe", "/c", "start", "", launch_target], shell=False)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", launch_target])
            else:
                subprocess.Popen(launch_target, shell=True)
            time.sleep(1.0)
            if pygetwindow is not None:
                try:
                    app_key = app_name.lower()
                    windows = [
                        window for window in pygetwindow.getAllWindows()
                        if app_key in window.title.lower()
                    ]
                    if windows:
                        windows[-1].restore()
                        windows[-1].activate()
                except Exception:
                    pass
            self._log("open_application", "completed", {"app": app_name, "target": launch_target})
            return {"status": "completed", "app": app_name, "target": launch_target}
        except Exception as exc:  # pragma: no cover
            self._log("open_application", "failed", {"app": app_name, "target": launch_target, "error": str(exc)})
            return {"status": "failed", "error": str(exc)}

    def click_at(self, x: int, y: int, clicks: int = 1, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        if dry_run:
            return {"status": "dry_run", "action": "click", "x": x, "y": y, "clicks": clicks}

        pyautogui.click(x=x, y=y, clicks=clicks)
        self._log("click_at", "completed", {"x": x, "y": y, "clicks": clicks})
        return {"status": "completed", "x": x, "y": y}

    def type_text(self, text: str, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        if dry_run:
            return {"status": "dry_run", "message": f"Would type: {text}"}

        if any(ord(character) > 127 for character in text) and pyperclip is not None:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.write(text)
        self._log("type_text", "completed", {"text": text})
        return {"status": "completed", "typed": text}

    def press_key(self, key: str, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        if dry_run:
            return {"status": "dry_run", "message": f"Would press {key}"}

        pyautogui.press(key)
        self._log("press_key", "completed", {"key": key})
        return {"status": "completed", "key": key}

    def search_web(self, query: str, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        if dry_run:
            return {"status": "dry_run", "message": f"Would search web for: {query}"}

        self._recover_pointer_from_corner()
        pyautogui.hotkey("ctrl", "l")
        self.type_text(query)
        pyautogui.press("enter")
        self._log("search_web", "completed", {"query": query})
        return {"status": "completed", "query": query}

    def open_url(self, url: str, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        url = url.strip()
        if not url:
            return {"status": "failed", "error": "url is required"}
        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = f"https://{url}"
        if dry_run:
            return {"status": "dry_run", "url": url}

        webbrowser.open(url)
        self._log("open_url", "completed", {"url": url})
        return {"status": "completed", "url": url}

    def _recover_pointer_from_corner(self) -> None:
        """Move the pointer out of PyAutoGUI's emergency corner without disabling fail-safe."""
        x, y = pyautogui.position()
        width, height = pyautogui.size()
        if x <= 1 or y <= 1 or x >= width - 2 or y >= height - 2:
            if os.name == "nt":
                import ctypes
                ctypes.windll.user32.SetCursorPos(width // 2, height // 2)
            else:
                pyautogui.moveTo(width // 2, height // 2)

    def wait(self, seconds: float, dry_run: bool = False) -> Dict[str, Any]:
        if dry_run:
            return {"status": "dry_run", "seconds": seconds}

        time.sleep(seconds)
        self._log("wait", "completed", {"seconds": seconds})
        return {"status": "completed", "seconds": seconds}

    def move_mouse(self, x: int, y: int, dry_run: bool = False) -> Dict[str, Any]:
        if not dry_run and not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop control is disabled"}

        if dry_run:
            return {"status": "dry_run", "action": "move_mouse", "x": x, "y": y}

        pyautogui.moveTo(x, y)
        self._log("move_mouse", "completed", {"x": x, "y": y})
        return {"status": "completed", "x": x, "y": y}

    def parse_instruction(self, instruction: str) -> Dict[str, Any]:
        text = instruction.strip()
        if not text:
            raise ValueError("instruction is empty")

        lowered = text.lower()

        if re.search(r"\b(screenshot|screen shot|capture screen)\b", lowered):
            return {"action": "screenshot"}

        match_url = re.search(r"\bopen\s+url(?:\s*:\s*|\s+)(https?://\S+)", text, re.IGNORECASE)
        if match_url:
            return {"action": "open_url", "value": match_url.group(1).strip().strip('"\'')}

        match_open = re.search(r"\bopen\s+(?:the\s+)?(?:app\s*:\s*|app\s+)?(.+)", text, re.IGNORECASE)
        if match_open:
            return {"action": "open_app", "value": match_open.group(1).strip().strip('"\'')}

        match_click = re.search(r"\bclick(?:\s+at)?\s+(\d+)\s+(\d+)\b", lowered)
        if match_click:
            return {"action": "click_at", "x": int(match_click.group(1)), "y": int(match_click.group(2))}

        match_type = re.search(r"\btype\s+(?:text\s*:\s*|text\s+)?(.+)", text, re.IGNORECASE)
        if match_type:
            return {"action": "type_text", "value": match_type.group(1).strip().strip('"\'')}

        match_search = re.search(r"\bsearch\s+(?:the\s+web\s+|web\s+|for\s+)?(.+)", text, re.IGNORECASE)
        if match_search:
            return {"action": "search_web", "value": match_search.group(1).strip().strip('"\'')}

        match_press = re.search(r"\bpress\s+(.+)", lowered)
        if match_press:
            return {"action": "press_key", "value": match_press.group(1).strip()}

        match_wait = re.search(r"\bwait\s+(\d+(?:\.\d+)?)\s*(?:second|seconds|sec|s)?\b", lowered)
        if match_wait:
            return {"action": "wait", "value": float(match_wait.group(1))}

        match_move = re.search(r"\bmove\s+(?:mouse\s+)?to\s+(\d+)\s+(\d+)\b", lowered)
        if match_move:
            return {"action": "move_mouse", "x": int(match_move.group(1)), "y": int(match_move.group(2))}

        if re.search(r"\b(hello|hi)\b", lowered):
            return {"action": "type_text", "value": "Hello!"}

        raise ValueError(f"unsupported instruction: {instruction}")

    def _split_steps(self, prompt: str) -> List[str]:
        steps = re.split(r"\s+(?:then|and then|,|;)\s+", prompt.strip())
        if len(steps) == 1:
            return [prompt.strip()]
        return [step.strip() for step in steps if step.strip()]

    def analyze_screen(self, screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """Basic vision layer: inspect a screenshot and report whether OCR is available."""
        if screenshot_path is None:
            screenshot_path = os.path.join(self.capture_dir, f"screen_{int(time.time())}.png")

        if not os.path.exists(screenshot_path):
            return {"status": "failed", "error": f"Screenshot not found: {screenshot_path}"}

        try:
            from PIL import Image
            with Image.open(screenshot_path) as image:
                width, height = image.size
                result = {
                    "status": "completed",
                    "path": screenshot_path,
                    "size": {"width": width, "height": height},
                    "ocr_available": False,
                    "summary": "Image captured successfully; OCR is optional and only works if Tesseract is installed.",
                }

            try:
                import pytesseract  # type: ignore
                text = pytesseract.image_to_string(Image.open(screenshot_path))
                result["ocr_available"] = bool(text and text.strip())
                result["ocr_text"] = text.strip()[:2000]
                if text and text.strip():
                    result["summary"] = "Screen image captured and OCR text was extracted."
            except Exception:
                pass

            return result
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "error": str(exc)}

    def _call_local_llm(self, prompt: str) -> Optional[str]:
        """Return a local model response for structured NLP normalization."""
        if ollama is not None:
            try:
                response = ollama.generate(model=self.local_model, prompt=prompt)
                return response.get("response", "")
            except Exception:
                pass

        if requests is None:
            return None

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.local_model, "prompt": prompt, "stream": False},
                timeout=3,
            )
            if response.status_code == 200:
                return response.json().get("response", "")
        except Exception:
            pass
        return None

    def _try_local_model_plan(self, prompt: str) -> Optional[List[str]]:
        planning_prompt = (
            "Convert this instruction into desktop actions. Output ONLY one action per line, "
            "with no numbering, explanations, labels, or colons. Use exactly these forms: "
            "open <app>, click at <x> <y>, type <text>, press <key>, wait <seconds>, "
            "take screenshot. Preserve the user's typed text exactly.\nInstruction: " + prompt
        )

        if ollama is not None:
            try:
                response = ollama.generate(model=self.local_model, prompt=planning_prompt)
                content = response.get("response", "")
                lines = self._finalize_model_steps(self._normalize_model_steps(content), prompt)
                if lines:
                    return lines
            except Exception:
                pass

        if requests is None:
            return None

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.local_model,
                        "prompt": planning_prompt,
                    "stream": False,
                },
                timeout=3,
            )
            if response.status_code != 200:
                return None
            content = response.json().get("response", "")
            lines = self._finalize_model_steps(self._normalize_model_steps(content), prompt)
            return lines or None
        except Exception:
            return None

    def _normalize_model_steps(self, content: str) -> List[str]:
        """Convert common local-model prose into the parser's action syntax."""
        normalized = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            line = re.sub(r"^(?:[-*]|\d+[.)])\s*", "", line)
            line = re.sub(r"^(?:here is .*?:|action:)\s*", "", line, flags=re.IGNORECASE)
            line = re.sub(r"\s+\([^)]*\)", "", line)
            line = line.strip().strip("`\"")
            lowered = line.lower()

            if re.match(r"^open\s+(?:app\s*:\s*|app\s+)?", lowered):
                value = re.sub(r"^open\s+(?:app\s*:\s*|app\s+)?", "", line, flags=re.IGNORECASE).strip().strip("\"")
                if value:
                    normalized.append(f"open {value}")
            elif re.match(r"^(?:search|search web|search for)\s+", lowered):
                value = re.sub(r"^(?:search\s+web|search\s+for|search)\s+", "", line, flags=re.IGNORECASE).strip().strip("\"")
                if value:
                    normalized.append(f"search web {value}")
            elif re.match(r"^type\s+(?:text\s*:\s*|text\s+)?", lowered):
                value = re.sub(r"^type\s+(?:text\s*:\s*|text\s+)?", "", line, flags=re.IGNORECASE).strip().strip("\"")
                if value:
                    normalized.append(f"type {value}")
            elif re.match(r"^press\s+(?:key\s+)?", lowered):
                value = re.sub(r"^press\s+(?:key\s+)?", "", line, flags=re.IGNORECASE).strip().strip("\"")
                if value:
                    normalized.append(f"press {value}")
            elif re.match(r"^(?:take\s+)?screenshot", lowered):
                normalized.append("take screenshot")
            elif re.match(r"^wait\s+", lowered) or re.match(r"^click(?:\s+at)?\s+\d+", lowered):
                normalized.append(line)

        return normalized

    def _finalize_model_steps(self, steps: List[str], prompt: str) -> List[str]:
        """Keep generated actions faithful to the user's original request."""
        prompt_lower = prompt.lower()
        enter_requested = bool(re.search(r"\b(enter|return)\b|\bpress\b.*\benter\b", prompt_lower))
        search_requested = bool(re.search(r"\b(search|look up|google)\b", prompt_lower))
        click_requested = bool(re.search(r"\bclick\b", prompt_lower))
        wait_requested = bool(re.search(r"\bwait\b|\bafter\s+\d+\s+seconds?", prompt_lower))
        screenshot_requested = bool(re.search(r"\bscreenshot\b|\bscreen shot\b|\bcapture screen\b", prompt_lower))
        search_query = self._extract_search_query(prompt) if search_requested else None
        finalized = []

        for step in steps:
            lowered = step.lower().strip()
            if lowered.startswith("click ") and not click_requested:
                continue
            if lowered.startswith("wait ") and not wait_requested:
                continue
            if lowered == "take screenshot" and not screenshot_requested:
                continue
            if lowered in {"press enter", "press return"} and not enter_requested:
                continue
            if lowered.startswith("press ") and not enter_requested and not re.search(r"\bpress\b", prompt_lower):
                continue

            if lowered.startswith("type "):
                value = step[5:].strip()
                if search_query and any(item.lower().startswith("open ") for item in finalized):
                    step = f"search web {search_query}"
                    lowered = step.lower()
                if re.search(r"\s+nu$", value, re.IGNORECASE) and re.search(r"\bnu\s+type\b", prompt_lower):
                    value = re.sub(r"\s+nu$", "", value, flags=re.IGNORECASE)
                value = re.sub(r"\s+\u0b8e\u0ba9\u0bcd\u0bb1\u0bc1$", "", value)
                if lowered.startswith("type "):
                    step = f"type {value}"

            finalized.append(step)

        if search_query and any(item.lower().startswith("open ") for item in finalized):
            finalized = [item for item in finalized if not item.lower().startswith("search web ")]
            finalized.append(f"search web {search_query}")

        return finalized

    def _extract_search_query(self, prompt: str) -> Optional[str]:
        """Extract the user's search terms without letting the model invent them."""
        patterns = [
            r"(.+?)\s+(?:search|thedu|thedi)\s+(?:pannu|pan|please)?$",
            r"\bsearch\s+(?:the\s+web\s+|web\s+|for\s+)?(.+)$",
            r"\b(?:look\s+up|google)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, prompt.strip(), re.IGNORECASE)
            if match:
                query = match.group(1).strip().strip(" .,:;\"'")
                query = re.sub(r"^.*\b(?:and|panni|pannu)\s+", "", query, flags=re.IGNORECASE)
                query = re.sub(r"\s+(?:pannu|pan|please)$", "", query, flags=re.IGNORECASE).strip()
                if query:
                    return query
        return None

    def execute_instruction(
        self,
        instruction: str,
        allow_desktop_control: Optional[bool] = None,
        dry_run: bool = False,
        agent_id: Optional[str] = None,
        access_token: Optional[str] = None,
        consent: bool = True,
        action_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if allow_desktop_control is not None:
            self.allow_desktop_control = allow_desktop_control
        else:
            self.allow_desktop_control = self.authorize(agent_id, access_token, consent)

        if not self.allow_desktop_control:
            return {"status": "blocked", "reason": "desktop access requires local laptop consent and permission guard approval"}

        screen_context = self.refresh_screen_context()
        if screen_context.get("status") != "completed":
            return {"status": "blocked", "reason": screen_context.get("reason", screen_context.get("error", "screen access failed"))}

        if action_name:
            if not self.guard.allow_action(action_name):
                return {"status": "blocked", "reason": f"sentinel guard blocked {action_name}; admin approval required"}

        prompt = instruction.strip()
        if not prompt:
            return {"status": "failed", "error": "empty instruction"}

        steps = self._try_local_model_plan(prompt) or self._split_steps(prompt)
        results = []

        for step in steps:
            try:
                parsed = self.parse_instruction(step)
                action = parsed["action"]

                if action == "screenshot":
                    result = self.take_screenshot(dry_run=dry_run)
                elif action == "open_app":
                    result = self.open_application(parsed["value"], dry_run=dry_run)
                elif action == "click_at":
                    result = self.click_at(parsed["x"], parsed["y"], dry_run=dry_run)
                elif action == "type_text":
                    result = self.type_text(parsed["value"], dry_run=dry_run)
                elif action == "search_web":
                    result = self.search_web(parsed["value"], dry_run=dry_run)
                elif action == "open_url":
                    result = self.open_url(parsed["value"], dry_run=dry_run)
                elif action == "press_key":
                    result = self.press_key(parsed["value"], dry_run=dry_run)
                elif action == "wait":
                    result = self.wait(parsed["value"], dry_run=dry_run)
                elif action == "move_mouse":
                    result = self.move_mouse(parsed["x"], parsed["y"], dry_run=dry_run)
                else:
                    result = {"status": "failed", "error": f"Unsupported action: {action}"}

                results.append({"instruction": step, "result": result})
            except ValueError as exc:
                results.append({"instruction": step, "result": {"status": "failed", "error": str(exc)}})

        return {
            "status": "completed" if all(item["result"].get("status") in {"completed", "dry_run"} for item in results) else "partial",
            "results": results,
            "execution_log": self.execution_log[-10:],
        }

    def listen_voice_command(self, timeout: int = 10) -> Dict[str, Any]:
        return self.voice.listen_for_command(timeout=timeout)

    def live_voice_control(self, operation: str, command_handler=None, status_handler=None) -> Dict[str, Any]:
        if operation == "listen":
            return self.listen_voice_command(timeout=10)
        if operation == "start_live":
            return self.voice.start_live_listening(command_handler, status_handler)
        if operation == "stop_live":
            return self.voice.stop_live_listening()
        return {"status": "failed", "error": f"unknown live voice operation: {operation}"}

    def start_overlay(self):
        self.overlay.set_callbacks(
            command_handler=self.execute_from_overlay,
            voice_handler=self.live_voice_control,
            refresh_handler=self.refresh_screen_context,
        )
        return self.overlay.start(command_handler=self.execute_from_overlay, voice_handler=self.live_voice_control)


def demo():
    agent = LocalInstructionAgent(allow_desktop_control=True, local_laptop_mode=True, permission_guard=True)
    prompt = "take screenshot then open notepad then type hello then press enter"
    result = agent.execute_instruction(prompt, allow_desktop_control=True, dry_run=True)
    print(result)


if __name__ == "__main__":
    demo()
