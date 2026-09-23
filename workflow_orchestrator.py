"""Priority 7 workflow planning for long, multi-application requests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowSpec:
    workflow_id: str
    title: str
    domains: List[str]
    steps: List[str]
    verification: List[str]
    required_inputs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "title": self.title,
            "domains": self.domains,
            "steps": self.steps,
            "verification": self.verification,
            "required_inputs": self.required_inputs,
        }


class WorkflowOrchestrator:
    """Classify long requests into auditable plans without executing actions."""

    SPECS = {
        "multi_tab_research": WorkflowSpec(
            "multi_tab_research", "Multi-tab research", ["browser", "research", "file"],
            ["open browser", "create one tab per topic", "search each topic", "read page state and relevant text", "extract five facts per topic", "write grouped report with source titles"],
            ["tab count", "five facts per topic", "source title beside every fact", "report file exists"],
            ["three topics", "output file path"],
        ),
        "download_organize_rename": WorkflowSpec(
            "download_organize_rename", "Download and organize files", ["browser", "filesystem"],
            ["download three public sample files", "confirm downloads", "create Agent_Test_2026", "move files", "rename by file type"],
            ["three files exist", "folder exists", "names match types"],
            ["three public file URLs"],
        ),
        "form_filling": WorkflowSpec(
            "form_filling", "Test form filling", ["browser", "form"],
            ["open designated public test form", "inspect fields", "fill only Test User/test@example.com/0000000000", "review fields", "submit only after validation"],
            ["field values match", "no real personal data", "submission result"],
            ["public form URL"],
        ),
        "cross_application": WorkflowSpec(
            "cross_application", "Cross-application copy and paste", ["browser", "desktop", "file"],
            ["open source page", "extract three pieces of information", "open text editor", "write structured table", "save cross_app_test.txt", "verify saved contents"],
            ["three values copied", "file exists", "file contents match"],
            ["source page URL"],
        ),
        "browser_session": WorkflowSpec(
            "browser_session", "Browser session management", ["browser"],
            ["open five test pages", "track tab identities", "reorder tabs", "pin requested tab", "duplicate requested tab", "close two tabs", "return to requested page"],
            ["final tab order", "pinned tab", "duplicate tab", "requested page active"],
            ["five page URLs", "tab order", "pinned tab", "duplicate tab"],
        ),
        "search_filter_extract": WorkflowSpec(
            "search_filter_extract", "Search, filter, and extract", ["browser", "research", "file"],
            ["open designated dataset", "apply named filters", "verify matching records", "extract first five", "write local result file"],
            ["filters visible", "five records", "file contents match"],
            ["dataset URL", "filter criteria", "output file path"],
        ),
        "error_recovery": WorkflowSpec(
            "error_recovery", "Harmless error recovery", ["browser", "verification", "recovery"],
            ["open designated test page", "perform harmless invalid test input", "read error message", "correct value", "verify continuation"],
            ["error observed", "corrected value accepted", "workflow continued"],
            ["test page URL", "invalid and corrected values"],
        ),
        "file_verification": WorkflowSpec(
            "file_verification", "File content verification", ["filesystem", "file"],
            ["create three dummy text files", "open each file", "verify exact contents", "write one-line summaries", "save summary file"],
            ["three files found", "contents verified", "summary exists"],
            ["file contents", "summary file path"],
        ),
        "sequential_workflow": WorkflowSpec(
            "sequential_workflow", "Long sequential workflow", ["browser", "desktop", "file", "verification"],
            ["open browser", "navigate designated site", "locate specified information", "copy to editor", "save under Agent_Test_2026", "reopen and verify", "report outcome"],
            ["source located", "saved file exists", "reopened contents match", "final status"],
            ["website URL", "information target", "output filename"],
        ),
        "window_stress": WorkflowSpec(
            "window_stress", "Window-management stress test", ["desktop", "window management"],
            ["open browser, Explorer, text editor, Calculator", "arrange browser and editor visibly", "switch through all four", "perform harmless action in each", "verify applications remain responsive"],
            ["four windows detected", "browser/editor visible", "one action per app"],
            [],
        ),
    }

    def plan(self, request: str) -> Dict[str, Any]:
        text = (request or "").strip()
        workflow_id = self._classify(text)
        if workflow_id is None:
            return {"status": "unknown", "needs_clarification": True, "message": "I could not identify a supported multi-step workflow."}
        spec = self.SPECS[workflow_id]
        missing = [item for item in spec.required_inputs if not self._has_input(text, item)]
        return {
            "status": "needs_clarification" if missing else "planned",
            "needs_clarification": bool(missing),
            "workflow": spec.to_dict(),
            "missing_inputs": missing,
            "message": "Provide the missing workflow inputs before execution." if missing else "Workflow is ready for execution.",
        }

    def _classify(self, text: str) -> Optional[str]:
        lowered = text.lower()
        patterns = {
            "multi_tab_research": ("three tabs", "three different topics", "research three topics", "research topics", "five specific facts", "extract five facts", "grouped by topic", "save a report", "save it as"),
            "download_organize_rename": ("download", "move the files", "rename them", "agent_test_2026"),
            "form_filling": ("test form", "test@example.com", "fill", "submit"),
            "cross_application": ("copy three", "text editor", "cross_app_test.txt"),
            "browser_session": ("five different", "rearrange the tabs", "pin", "duplicate", "close two tabs"),
            "search_filter_extract": ("dataset", "filters", "first five", "matching records"),
            "error_recovery": ("invalid value", "error message", "correct it"),
            "file_verification": ("three dummy text files", "verify the contents", "summary file"),
            "sequential_workflow": ("starting from the desktop", "starting from desktop", "reopen the saved document", "complete workflow"),
            "window_stress": ("file explorer", "calculator", "side by side", "switch between all four"),
        }
        scores = {workflow_id: sum(term in lowered for term in terms) for workflow_id, terms in patterns.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] >= 2 else None

    @staticmethod
    def _has_input(text: str, required: str) -> bool:
        lowered = text.lower()
        if required == "three topics":
            return bool(re.search(r"topics?\s*[:=]\s*[^.;]+", lowered))
        if required in {"output file path", "summary file path", "output filename"}:
            return bool(re.search(r"(?:save|write|file)\s+(?:it\s+)?(?:as|to|at)\s+\S+\.(?:txt|md|csv|json)", lowered))
        if required in {"three public file urls", "five page urls"}:
            return len(re.findall(r"https?://", lowered)) >= (3 if required == "three public file urls" else 5)
        if required in {"tab order", "pinned tab", "duplicate tab", "filter criteria", "invalid and corrected values", "file contents", "information target"}:
            return bool(re.search(r"https?://|file|criteria|target|order|pin|duplicate|invalid|correct|content", lowered))
        if required in {"public form url", "source page url", "dataset url", "test page url", "website url"}:
            return "http://" in lowered or "https://" in lowered
        return False
