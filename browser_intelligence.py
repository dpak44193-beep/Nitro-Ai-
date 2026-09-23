"""Priority 6 browser intelligence using Playwright."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class BrowserIntelligence:
    """DOM-aware browser automation kept separate from desktop automation."""

    def __init__(self, browser_name: str = "edge", headless: bool = False, timeout: int = 10000):
        self.browser_name = browser_name
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.started = False

    def start(self) -> Dict[str, Any]:
        if self.started and self.page:
            return {"status": "already_running", "url": self.page.url}
        try:
            self.playwright = sync_playwright().start()
            args: Dict[str, Any] = {"headless": self.headless}
            executable = self._find_browser_executable()
            if executable:
                args["executable_path"] = executable
            self.browser = self.playwright.chromium.launch(**args)
            self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            self.started = True
            return {"status": "started", "browser": self.browser_name, "url": self.page.url}
        except Exception as exc:
            self.close()
            return {"status": "failed", "error": str(exc)}

    def _find_browser_executable(self) -> Optional[str]:
        if os.name != "nt":
            return None
        name = self.browser_name.lower()
        if name == "edge":
            candidates = [
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ]
        elif name == "chrome":
            candidates = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ]
        else:
            candidates = []
        return next((path for path in candidates if os.path.exists(path)), None)

    def _ensure_started(self) -> bool:
        return self.started and self.page is not None or self.start().get("status") in {"started", "already_running"}

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "failed", "error": "browser_not_started"}
        url = url if url.startswith(("http://", "https://")) else f"https://{url}"
        try:
            response = self.page.goto(url, wait_until=wait_until, timeout=self.timeout)
            return {"status": "completed", "url": self.page.url, "title": self.page.title(), "http_status": response.status if response else None}
        except PlaywrightTimeoutError:
            return {"status": "failed", "error": "navigation_timeout", "url": self.page.url, "title": self.page.title()}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "url": self.page.url}

    def _visible_data(self, selector: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self.page.locator(selector).evaluate_all(
            """(elements, limit) => elements.slice(0, limit).map((el, index) => ({
                index, text: (el.innerText || el.textContent || '').trim().slice(0, 500),
                aria_label: el.getAttribute('aria-label'), type: el.getAttribute('type'),
                name: el.getAttribute('name'), placeholder: el.getAttribute('placeholder'),
                href: el.href || null, disabled: !!el.disabled,
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
            }))""", limit
        )

    def get_page_state(self) -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "failed", "error": "browser_not_started"}
        try:
            return {
                "status": "completed", "url": self.page.url, "title": self.page.title(),
                "loading": self.page.evaluate("() => document.readyState !== 'complete'"),
                "buttons": self._visible_data("button, [role='button']"),
                "links": self._visible_data("a, [role='link']"),
                "inputs": self._visible_data("input, textarea, select"),
                "forms": self.page.locator("form").evaluate_all("(items) => items.slice(0, 50).map((form, index) => ({index, action: form.action, method: form.method, text: (form.innerText || '').trim().slice(0, 500)}))"),
                "errors": self._detect_page_errors(),
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def _detect_page_errors(self) -> List[str]:
        try:
            text = self.page.locator("body").inner_text(timeout=2000).lower()
            return [pattern for pattern in ("404", "403 forbidden", "500 internal server error", "page not found", "something went wrong", "unable to connect", "this site can't be reached", "access denied") if pattern in text]
        except Exception:
            return []

    def get_dom_snapshot(self, max_length: int = 20000) -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "failed", "error": "browser_not_started"}
        try:
            html = self.page.locator("body").inner_html()
            return {"status": "completed", "html": html[:max_length], "truncated": len(html) > max_length}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def _find(self, kind: str, name: str):
        if kind == "button":
            locator = self.page.get_by_role("button", name=name, exact=False)
            return locator if locator.count() else self.page.get_by_text(name, exact=False)
        locator = self.page.get_by_role("link", name=name, exact=False)
        return locator if locator.count() else self.page.get_by_text(name, exact=False)

    def find_button(self, name: str) -> Dict[str, Any]:
        return self._find_element("button", name)

    def find_link(self, name: str) -> Dict[str, Any]:
        return self._find_element("link", name)

    def _find_element(self, kind: str, name: str) -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "failed", "found": False, "error": "browser_not_started"}
        try:
            locator = self._find(kind, name)
            if not locator.count():
                return {"status": "not_found", "found": False, "target": name}
            return {"status": "found", "found": True, "target": name, "count": locator.count(), "text": locator.first.inner_text(timeout=2000)}
        except Exception as exc:
            return {"status": "failed", "found": False, "error": str(exc)}

    def click_button(self, name: str) -> Dict[str, Any]:
        return self._click_element("button", name)

    def click_link(self, name: str) -> Dict[str, Any]:
        return self._click_element("link", name)

    def _click_element(self, kind: str, name: str) -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "failed", "error": "browser_not_started"}
        try:
            locator = self._find(kind, name)
            if not locator.count():
                return {"status": "failed", "error": f"{kind}_not_found:{name}"}
            locator.first.click(timeout=self.timeout)
            return {"status": "completed", "action": f"click_{kind}", "target": name, "url": self.page.url, "title": self.page.title()}
        except PlaywrightTimeoutError:
            return {"status": "failed", "error": f"{kind}_click_timeout:{name}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def fill_input(self, target: str, value: str) -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "failed", "error": "browser_not_started"}
        try:
            locator = self.page.get_by_role("textbox", name=target, exact=False)
            if not locator.count():
                locator = self.page.locator(f"input[placeholder*='{target}'], input[name*='{target}']")
            if not locator.count():
                return {"status": "failed", "error": f"input_not_found:{target}"}
            locator.first.fill(value, timeout=self.timeout)
            return {"status": "completed", "action": "fill_input", "target": target, "value": value}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def search_google(self, query: str) -> Dict[str, Any]:
        result = self.navigate("https://www.google.com")
        if result.get("status") != "completed":
            return result
        try:
            search_box = self.page.get_by_role("textbox", name="Search", exact=False)
            if not search_box.count():
                search_box = self.page.locator("textarea[name='q'], input[name='q']")
            search_box.first.fill(query, timeout=self.timeout)
            search_box.first.press("Enter")
            self.page.wait_for_load_state("domcontentloaded", timeout=self.timeout)
            return {"status": "completed", "action": "search", "query": query, "url": self.page.url, "title": self.page.title()}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "query": query}

    def verify(self, expected: Dict[str, Any]) -> Dict[str, Any]:
        if not self._ensure_started():
            return {"status": "FAILURE", "reason": "browser_not_started"}
        url, title = self.page.url, self.page.title()
        if expected.get("url") and expected["url"].lower() not in url.lower():
            return {"status": "FAILURE", "reason": "expected_url_not_found", "expected": expected["url"], "actual": url}
        if expected.get("title") and expected["title"].lower() not in title.lower():
            return {"status": "FAILURE", "reason": "expected_title_not_found", "expected": expected["title"], "actual": title}
        if expected.get("text"):
            try:
                body = self.page.locator("body").inner_text(timeout=2000)
                if expected["text"].lower() not in body.lower():
                    return {"status": "FAILURE", "reason": "expected_text_not_found", "expected": expected["text"]}
            except Exception as exc:
                return {"status": "FAILURE", "reason": str(exc)}
        return {"status": "VERIFIED", "url": url, "title": title}

    def close(self) -> None:
        for resource in (self.context, self.browser, self.playwright):
            try:
                if resource:
                    resource.close() if resource is not self.playwright else resource.stop()
            except Exception:
                pass
        self.page = self.context = self.browser = self.playwright = None
        self.started = False
