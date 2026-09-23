"""Priority 8: persistent episodic task memory."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class TaskMemory:
    """Store task episodes and recommend methods from verified history."""

    def __init__(self, db_path: str = "task_memory.db"):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS task_memory (
                    task_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, task TEXT NOT NULL,
                    normalized_task TEXT, input_data TEXT, plan TEXT, actions TEXT,
                    result TEXT, failure TEXT, recovery TEXT, final_status TEXT,
                    successful_method TEXT, retry_count INTEGER DEFAULT 0,
                    verification TEXT, method_confidence REAL DEFAULT 0.0,
                    method_uses INTEGER DEFAULT 0, method_successes INTEGER DEFAULT 0,
                    method_failures INTEGER DEFAULT 0
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_task_normalized ON task_memory(normalized_task)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON task_memory(final_status)")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(task_memory)")}
            for name, definition in {
                "method_confidence": "REAL DEFAULT 0.0",
                "method_uses": "INTEGER DEFAULT 0",
                "method_successes": "INTEGER DEFAULT 0",
                "method_failures": "INTEGER DEFAULT 0",
            }.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE task_memory ADD COLUMN {name} {definition}")

    def create_task(self, task: str, normalized_task: Optional[str] = None, input_data: Optional[Dict[str, Any]] = None, plan: Optional[List[Dict[str, Any]]] = None) -> str:
        task_id = str(uuid.uuid4())[:16]
        values = (task_id, datetime.now().isoformat(), task, normalized_task or task.lower().strip(), json.dumps(input_data or {}, default=str), json.dumps(plan or [], default=str))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("INSERT INTO task_memory (task_id,timestamp,task,normalized_task,input_data,plan,actions,result,failure,recovery,final_status,verification) VALUES (?,?,?,?,?,?,?, ?,?,?,?,?)", values + ("[]", "{}", "{}", "[]", "RUNNING", "{}"))
        return task_id

    def _load_json(self, value: Optional[str], default: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return default

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("SELECT task_id,timestamp,task,normalized_task,input_data,plan,actions,result,failure,recovery,final_status,successful_method,retry_count,verification,method_confidence,method_uses,method_successes,method_failures FROM task_memory WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            return None
        keys = ("task_id", "timestamp", "task", "normalized_task", "input_data", "plan", "actions", "result", "failure", "recovery", "final_status", "successful_method", "retry_count", "verification", "method_confidence", "method_uses", "method_successes", "method_failures")
        data = dict(zip(keys, row))
        for key, default in (("input_data", {}), ("plan", []), ("actions", []), ("result", {}), ("failure", {}), ("recovery", []), ("verification", {})):
            data[key] = self._load_json(data[key], default)
        return data

    def record_action(self, task_id: str, action: Dict[str, Any]) -> None:
        current = self.get_task(task_id)
        if current is None:
            return
        actions = current["actions"] if isinstance(current["actions"], list) else []
        actions.append({"timestamp": datetime.now().isoformat(), **action})
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE task_memory SET actions=? WHERE task_id=?", (json.dumps(actions, default=str), task_id))

    def record_result(self, task_id: str, result: Dict[str, Any], verification: Optional[Dict[str, Any]] = None) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE task_memory SET result=?, verification=? WHERE task_id=?", (json.dumps(result, default=str), json.dumps(verification or {}, default=str), task_id))

    def record_failure(self, task_id: str, failure: Dict[str, Any]) -> None:
        current = self.get_task(task_id)
        if current is None:
            return
        failures = current["failure"] if isinstance(current["failure"], dict) else {}
        failures.setdefault("events", []).append({"timestamp": datetime.now().isoformat(), **failure})
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE task_memory SET failure=?, retry_count=retry_count+1 WHERE task_id=?", (json.dumps(failures, default=str), task_id))

    def record_recovery(self, task_id: str, recovery: Dict[str, Any]) -> None:
        current = self.get_task(task_id)
        if current is None:
            return
        history = current["recovery"] if isinstance(current["recovery"], list) else []
        history.append({"timestamp": datetime.now().isoformat(), **recovery})
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE task_memory SET recovery=? WHERE task_id=?", (json.dumps(history, default=str), task_id))

    def complete_task(self, task_id: str, final_status: str, successful_method: Optional[str] = None) -> None:
        method = successful_method or "direct_execution"
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("SELECT method_uses,method_successes,method_failures FROM task_memory WHERE task_id=?", (task_id,)).fetchone()
            uses, successes, failures = row or (0, 0, 0)
            uses += 1
            if final_status in {"SUCCESS", "RECOVERED", "COMPLETED"}:
                successes += 1
            else:
                failures += 1
            confidence = round(successes / uses, 3) if uses else 0.0
            connection.execute("UPDATE task_memory SET final_status=?,successful_method=?,method_confidence=?,method_uses=?,method_successes=?,method_failures=? WHERE task_id=?", (final_status, method, confidence, uses, successes, failures, task_id))

    def search(self, task: str, limit: int = 10) -> List[Dict[str, Any]]:
        normalized = task.lower().strip()
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute("SELECT task_id FROM task_memory WHERE lower(normalized_task) LIKE ? OR lower(task) LIKE ? ORDER BY timestamp DESC LIMIT ?", (f"%{normalized}%", f"%{normalized}%", limit)).fetchall()
        return [self.get_task(row[0]) for row in rows if self.get_task(row[0]) is not None]

    def find_successful_method(self, task: str) -> Optional[Dict[str, Any]]:
        successes = [item for item in self.search(task) if item["final_status"] in {"SUCCESS", "RECOVERED", "COMPLETED"}]
        if not successes:
            return None
        best = max(successes, key=lambda item: (item.get("method_confidence", 0.0), item.get("timestamp", "")))
        return {"task_id": best["task_id"], "task": best["task"], "method": best["successful_method"], "confidence": best.get("method_confidence", 0.0), "uses": best.get("method_uses", 0), "actions": best["actions"], "result": best["result"], "verification": best["verification"]}

    def find_previous_failures(self, task: str) -> List[Dict[str, Any]]:
        return [{"task_id": item["task_id"], "task": item["task"], "failure": item["failure"], "recovery": item["recovery"]} for item in self.search(task, 20) if item["failure"]]
