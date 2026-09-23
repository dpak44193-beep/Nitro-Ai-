import time
import os
import hashlib
from typing import Dict, Any

import pyautogui

try:
    import pygetwindow
except ImportError:
    pygetwindow = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


class RealObserver:
    """Observe the real desktop state after an action and verify expectations."""

    def __init__(self, capture_dir="captures"):
        self.capture_dir = capture_dir
        os.makedirs(self.capture_dir, exist_ok=True)

    def screenshot(self, name="screen"):
        filename = f"{name}_{int(time.time() * 1000)}.png"
        path = os.path.join(self.capture_dir, filename)
        image = pyautogui.screenshot()
        image.save(path)
        return path

    def get_windows(self):
        if pygetwindow is None:
            return []
        try:
            windows = pygetwindow.getAllWindows()
            return [
                window.title.strip()
                for window in windows
                if window.title and window.title.strip()
            ]
        except Exception:
            return []

    def check_window(self, expected_window):
        windows = self.get_windows()
        expected = expected_window.lower()
        matches = [window for window in windows if expected in window.lower()]
        return {
            "verified": len(matches) > 0,
            "expected": expected_window,
            "matches": matches,
            "visible_windows": windows,
        }

    def get_screen_text(self, screenshot_path):
        if pytesseract is None or Image is None:
            return ""
        try:
            image = Image.open(screenshot_path)
            return pytesseract.image_to_string(image).strip()
        except Exception:
            return ""

    def check_text(self, expected_text):
        screenshot_path = self.screenshot("verify")
        screen_text = self.get_screen_text(screenshot_path)
        found = expected_text.lower() in screen_text.lower()
        return {
            "verified": found,
            "expected": expected_text,
            "observed_text": screen_text,
            "screenshot": screenshot_path,
        }

    def get_hash(self, path):
        with open(path, "rb") as file:
            return hashlib.sha256(file.read()).hexdigest()

    def check_screen_changed(self, before, after):
        before_hash = self.get_hash(before)
        after_hash = self.get_hash(after)
        changed = before_hash != after_hash
        return {
            "verified": changed,
            "screen_changed": changed,
            "before": before,
            "after": after,
        }

    def verify(self, expected: Dict[str, Any], before_screen=None, wait=1.0):
        time.sleep(wait)
        after_screen = self.screenshot("after")

        if "window" in expected:
            result = self.check_window(expected["window"])
            if not result["verified"]:
                return {
                    "status": "FAILURE",
                    "reason": "Expected window not found",
                    "observation": result,
                }

        if "text" in expected:
            screen_text = self.get_screen_text(after_screen)
            if expected["text"].lower() not in screen_text.lower():
                return {
                    "status": "FAILURE",
                    "reason": "Expected text not found",
                    "expected": expected["text"],
                    "observed_text": screen_text,
                    "screenshot": after_screen,
                }

        if expected.get("screen_changed") and before_screen:
            result = self.check_screen_changed(before_screen, after_screen)
            if not result["verified"]:
                return {
                    "status": "FAILURE",
                    "reason": "Screen did not change",
                    "observation": result,
                }

        return {
            "status": "VERIFIED",
            "expected": expected,
            "screenshot": after_screen,
        }
