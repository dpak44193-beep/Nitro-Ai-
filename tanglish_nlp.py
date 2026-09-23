"""Priority 5: Tanglish and informal-language intent normalization."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

OPEN_APP = "OPEN_APP"
OPEN_BROWSER = "OPEN_BROWSER"
NAVIGATE_SEARCH = "NAVIGATE_SEARCH"
CLICK = "CLICK"
TYPE_TEXT = "TYPE_TEXT"
PRESS_KEY = "PRESS_KEY"
WAIT = "WAIT"
TAKE_SCREENSHOT = "TAKE_SCREENSHOT"
UNKNOWN = "UNKNOWN"

VALID_INTENTS = {
    OPEN_APP,
    OPEN_BROWSER,
    NAVIGATE_SEARCH,
    CLICK,
    TYPE_TEXT,
    PRESS_KEY,
    WAIT,
    TAKE_SCREENSHOT,
    UNKNOWN,
}


@dataclass
class StandardIntent:
    intent: str
    target: Optional[str] = None
    query: Optional[str] = None
    text: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    source: str = "tanglish_nlp"
    raw_input: str = ""
    normalized_input: str = ""
    needs_clarification: bool = False
    clarification_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TanglishNormalizer:
    """Convert natural language to a safe, structured intent without execution."""

    def __init__(self, llm_client=None, model: str = "llama3.2"):
        self.llm_client = llm_client
        self.model = model

    def normalize(self, raw_input: str) -> Dict[str, Any]:
        if not raw_input or not raw_input.strip():
            return StandardIntent(
                intent=UNKNOWN,
                raw_input=raw_input or "",
                needs_clarification=True,
                clarification_reason="Empty user input",
            ).to_dict()

        raw_input = raw_input.strip()
        normalized = self._normalize_text(raw_input)
        if self.llm_client is not None:
            llm_result = self._llm_normalize(raw_input, normalized)
            if llm_result is not None:
                return llm_result
        return self._fallback_normalize(raw_input, normalized)

    def _normalize_text(self, text: str) -> str:
        text = text.lower().strip()
        for pattern in (
            r"\bdei\b", r"\bda\b", r"\bbro\b", r"\bplease\b",
            r"\bya\b", r"\bpa\b", r"\bmachan\b", r"\bhey\b",
        ):
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

        replacements = {
            r"\b(?:thora|thoraa|thira|thoranum)\b": "open",
            r"\bopen\s+pan(?:nu|na|ra)\b": "open",
            r"\b(?:thedu|theda|thedanum)\b": "search",
            r"\bsearch\s+pan(?:nu|na|ra)\b": "search",
            r"\bclick\s+pan(?:nu|na|ra)\b": "click",
            r"\btype\s+pan(?:nu|na|ra)\b": "type",
            r"\bstart\s+pan(?:nu|na|ra)\b": "start",
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()

    def _llm_normalize(self, raw_input: str, normalized_input: str) -> Optional[Dict[str, Any]]:
        try:
            if callable(self.llm_client):
                response = self.llm_client(self._build_prompt(raw_input, normalized_input))
            elif hasattr(self.llm_client, "generate"):
                response = self.llm_client.generate(self._build_prompt(raw_input, normalized_input))
            else:
                return None
            return self._parse_llm_response(response, raw_input, normalized_input)
        except Exception:
            return None

    def _build_prompt(self, raw_input: str, normalized_input: str) -> str:
        return f"""You are a desktop command normalization layer. Do not execute anything.
Convert the request into exactly one JSON intent.

Supported intents: OPEN_APP, OPEN_BROWSER, NAVIGATE_SEARCH, CLICK, TYPE_TEXT, PRESS_KEY, WAIT, TAKE_SCREENSHOT, UNKNOWN.
Rules: never invent targets or queries; preserve actual query text; use UNKNOWN when ambiguous; confidence below 0.65 requires clarification.

RAW INPUT: {raw_input}
NORMALIZED INPUT: {normalized_input}

Return only JSON with keys: intent, target, query, text, parameters, confidence, needs_clarification, clarification_reason.
"""

    def _parse_llm_response(self, response: Any, raw_input: str, normalized_input: str) -> Optional[Dict[str, Any]]:
        if isinstance(response, dict):
            data = response
        else:
            text = str(response).strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None

        intent = str(data.get("intent", UNKNOWN)).upper()
        if intent not in VALID_INTENTS:
            intent = UNKNOWN
        confidence = self._safe_confidence(data.get("confidence", 0.0))
        needs_clarification = bool(data.get("needs_clarification", False)) or confidence < 0.65
        return StandardIntent(
            intent=intent,
            target=data.get("target"),
            query=data.get("query"),
            text=data.get("text"),
            parameters=data.get("parameters") or {},
            confidence=confidence,
            source="llm",
            raw_input=raw_input,
            normalized_input=normalized_input,
            needs_clarification=needs_clarification,
            clarification_reason=data.get("clarification_reason"),
        ).to_dict()

    def _fallback_normalize(self, raw_input: str, normalized: str) -> Dict[str, Any]:
        base = {
            "raw_input": raw_input,
            "normalized_input": normalized,
            "source": "fallback",
        }

        if "screenshot" in normalized or "screen shot" in normalized:
            return StandardIntent(intent=TAKE_SCREENSHOT, confidence=0.90, **base).to_dict()

        search_match = re.search(r"\bsearch\b(?:\s+(?:for|on google|google la))?\s+(.+)", normalized)
        if search_match is None:
            trailing_search = re.search(r"(.+?)\s+search$", normalized)
            if trailing_search:
                search_match = trailing_search
        if search_match:
            query = search_match.group(1).strip()
            query = re.sub(r"^(?:google|browser)\s+(?:la\s+)?(?:po\s+|open\s+)?(?:panni\s+)?", "", query)
            query = re.sub(r"\b(?:pannu|panra|please)\b", "", query).strip()
            if query:
                return StandardIntent(
                    intent=NAVIGATE_SEARCH, target="google", query=query,
                    confidence=0.70, **base,
                ).to_dict()

        known_app_match = re.search(
            r"\b(microsoft\s+edge|google\s+chrome|edge|chrome|notepad|calculator|vscode)\b",
            normalized,
        )
        if known_app_match and re.search(r"\b(start|open)\b", normalized):
            target = known_app_match.group(1)
            target = {"microsoft edge": "edge", "google chrome": "chrome"}.get(target, target)
            return StandardIntent(intent=OPEN_APP, target=target, confidence=0.70, **base).to_dict()

        browser_match = re.search(r"\bbrowser\b", normalized)
        if browser_match and re.search(r"\b(start|open)\b", normalized):
            target = "edge"
            return StandardIntent(intent=OPEN_BROWSER, target=target, confidence=0.70, **base).to_dict()

        open_match = re.search(r"\bopen\s+([a-zA-Z0-9 ._-]+)$", normalized)
        if open_match and open_match.group(1).strip():
            return StandardIntent(
                intent=OPEN_APP, target=open_match.group(1).strip(),
                confidence=0.70, **base,
            ).to_dict()

        return StandardIntent(
            intent=UNKNOWN,
            confidence=0.0,
            needs_clarification=True,
            clarification_reason="Could not determine a safe standard intent",
            **base,
        ).to_dict()

    @staticmethod
    def _safe_confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0


class IntentActionMapper:
    """Convert a normalized intent into the existing core action contract."""

    @staticmethod
    def to_action(intent: Dict[str, Any]) -> Dict[str, Any]:
        intent_name = intent.get("intent", UNKNOWN)
        if intent.get("needs_clarification") or intent_name == UNKNOWN:
            return {"action": None, "input_data": {}, "expected_outcome": {}, "error": "clarification_required"}

        if intent_name in {OPEN_APP, OPEN_BROWSER}:
            target = intent.get("target", "")
            return {"action": "open_app", "input_data": {"app": target}, "expected_outcome": {"window": target}}
        if intent_name == NAVIGATE_SEARCH:
            query = intent.get("query", "")
            return {"action": "search_web", "input_data": {"query": query}, "expected_outcome": {"text": query}}
        if intent_name == TYPE_TEXT:
            text = intent.get("text", "")
            return {"action": "type_text", "input_data": {"text": text}, "expected_outcome": {"text": text}}
        if intent_name == CLICK:
            parameters = intent.get("parameters") or {}
            return {"action": "click_at", "input_data": parameters, "expected_outcome": parameters.get("expected_state", {})}
        if intent_name == PRESS_KEY:
            parameters = intent.get("parameters") or {}
            return {"action": "press_key", "input_data": {"key": parameters.get("key", "")}, "expected_outcome": parameters.get("expected_state", {})}
        if intent_name == WAIT:
            parameters = intent.get("parameters") or {}
            return {"action": "wait", "input_data": {"seconds": parameters.get("seconds", 1)}, "expected_outcome": parameters.get("expected_state", {})}
        if intent_name == TAKE_SCREENSHOT:
            return {"action": "take_screenshot", "input_data": {}, "expected_outcome": {"screen_changed": False}}
        return {"action": None, "input_data": {}, "expected_outcome": {}, "error": "unknown_intent"}
