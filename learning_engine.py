"""Priority 9: adaptive skill learning without self-modifying source code."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

SKILL_CANDIDATE = "candidate"
SKILL_ACTIVE = "active"
SKILL_REVIEW = "review"
SKILL_RETIRED = "retired"


class LearningEngine:
    """Extract and promote reusable skills from verified task experiences."""

    def __init__(self, db_path: str = "agent_learning.db", min_successes: int = 3, promotion_confidence: float = 0.80):
        self.db_path = db_path
        self.min_successes = min_successes
        self.promotion_confidence = promotion_confidence
        self._initialize_database()

    def _initialize_database(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    experience_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                    raw_input TEXT, normalized_intent TEXT, target TEXT,
                    plan TEXT, actions TEXT, result TEXT, verification TEXT,
                    failure TEXT, recovery TEXT, final_status TEXT
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    skill_name TEXT, intent TEXT, target TEXT, phrase_patterns TEXT,
                    action_strategy TEXT, expected_state TEXT, success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0, confidence REAL DEFAULT 0.0,
                    status TEXT, last_used TEXT, last_verified TEXT
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS skill_events (
                    event_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                    skill_id TEXT, event_type TEXT, details TEXT
                )
            """)

    def record_experience(self, raw_input: str, normalized_intent: str, target: Optional[str], plan: Optional[List[Dict[str, Any]]], actions: Optional[List[Dict[str, Any]]], result: Optional[Dict[str, Any]], verification: Optional[Dict[str, Any]], failure: Optional[Dict[str, Any]], recovery: Optional[List[Dict[str, Any]]], final_status: str) -> str:
        experience_id = str(uuid.uuid4())[:16]
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("INSERT INTO experiences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (experience_id, datetime.now().isoformat(), raw_input, normalized_intent, target, json.dumps(plan or [], default=str), json.dumps(actions or [], default=str), json.dumps(result or {}, default=str), json.dumps(verification or {}, default=str), json.dumps(failure or {}, default=str), json.dumps(recovery or [], default=str), final_status))
        return experience_id

    def evaluate_experience(self, experience: Dict[str, Any]) -> Dict[str, Any]:
        status = str(experience.get("final_status", "")).upper()
        verification = experience.get("verification") or {}
        result = experience.get("result") or {}
        failure = experience.get("failure") or {}
        recovery = experience.get("recovery") or []
        score = 0.0
        reasons: List[str] = []
        if status in {"SUCCESS", "COMPLETED", "VERIFIED", "RECOVERED"}:
            score += 0.4; reasons.append("task_completed")
        if str(verification.get("status", "")).upper() in {"VERIFIED", "SUCCESS"}:
            score += 0.3; reasons.append("verified")
        if result:
            score += 0.1; reasons.append("result_present")
        if recovery:
            score += 0.1; reasons.append("recovered")
        elif status in {"SUCCESS", "COMPLETED"}:
            score += 0.15; reasons.append("clean_execution")
        if failure:
            score -= 0.2; reasons.append("failure_present")
        score = round(max(0.0, min(1.0, score)), 3)
        return {"score": score, "learnable": score >= 0.7, "reasons": reasons}

    def learn_from_experience(self, experience: Dict[str, Any]) -> Dict[str, Any]:
        evaluation = self.evaluate_experience(experience)
        self.record_experience(experience.get("raw_input", ""), experience.get("normalized_intent", ""), experience.get("target"), experience.get("plan"), experience.get("actions"), experience.get("result"), experience.get("verification"), experience.get("failure"), experience.get("recovery"), experience.get("final_status", "FAILED"))
        if not evaluation["learnable"] or not experience.get("raw_input") or not experience.get("normalized_intent"):
            return {"status": "ignored", "reason": "experience_not_good_enough_to_learn", "evaluation": evaluation}

        intent, target = experience["normalized_intent"], experience.get("target")
        skill = self._find_skill(intent, target)
        phrase = self._phrase_pattern(experience["raw_input"])
        strategy = experience.get("actions") or []
        expected = experience.get("verification") or {}
        if skill is None:
            skill_id = str(uuid.uuid4())[:16]
            now = datetime.now().isoformat()
            with sqlite3.connect(self.db_path) as connection:
                connection.execute("INSERT INTO skills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (skill_id, now, now, f"{intent}_{target or 'generic'}", intent, target, json.dumps([phrase]), json.dumps(strategy, default=str), json.dumps(expected, default=str), 1, 0, evaluation["score"], SKILL_CANDIDATE, None, now))
            self._event(skill_id, "CREATED", evaluation)
            return {"status": "candidate_created", "skill_id": skill_id, "confidence": evaluation["score"]}

        phrases = skill["phrase_patterns"]
        if phrase not in phrases:
            phrases.append(phrase)
        successes = skill["success_count"] + 1
        confidence = self._confidence(successes, skill["failure_count"])
        status = SKILL_ACTIVE if successes >= self.min_successes and confidence >= self.promotion_confidence else SKILL_CANDIDATE
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE skills SET updated_at=?,phrase_patterns=?,action_strategy=?,expected_state=?,success_count=?,confidence=?,status=?,last_verified=? WHERE skill_id=?", (datetime.now().isoformat(), json.dumps(phrases), json.dumps(strategy, default=str), json.dumps(expected, default=str), successes, confidence, status, datetime.now().isoformat(), skill["skill_id"]))
        self._event(skill["skill_id"], "PROMOTED" if status == SKILL_ACTIVE else "UPDATED", {"confidence": confidence, "status": status})
        return {"status": "skill_promoted" if status == SKILL_ACTIVE else "skill_updated", "skill_id": skill["skill_id"], "confidence": confidence, "skill_status": status}

    def record_skill_failure(self, skill_id: str, reason: str) -> None:
        skill = self.get_skill(skill_id)
        if skill is None:
            return
        failures = skill["failure_count"] + 1
        confidence = self._confidence(skill["success_count"], failures)
        status = SKILL_REVIEW if failures >= 3 and confidence < 0.6 else skill["status"]
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE skills SET failure_count=?,confidence=?,status=?,updated_at=? WHERE skill_id=?", (failures, confidence, status, datetime.now().isoformat(), skill_id))
        self._event(skill_id, "FAILURE", {"reason": reason, "confidence": confidence})

    def select_skill(self, raw_input: str, intent: Optional[str] = None, target: Optional[str] = None) -> Optional[Dict[str, Any]]:
        candidates = []
        for skill in self.list_skills(SKILL_ACTIVE):
            if intent and skill["intent"] != intent or target and skill["target"] != target:
                continue
            if any(skill["phrase_patterns"][i] in raw_input.lower() or raw_input.lower() in skill["phrase_patterns"][i] for i in range(len(skill["phrase_patterns"]))):
                candidates.append(skill)
        return max(candidates, key=lambda item: (item["confidence"], item["success_count"]), default=None)

    def _find_skill(self, intent: str, target: Optional[str]) -> Optional[Dict[str, Any]]:
        return next((skill for skill in self.list_skills() if skill["intent"] == intent and skill["target"] == target), None)

    @staticmethod
    def _phrase_pattern(text: str) -> str:
        return re.sub(r"\s+", " ", text.lower().strip())

    @staticmethod
    def _confidence(successes: int, failures: int) -> float:
        total = successes + failures
        if not total:
            return 0.0
        return round(min(0.99, 0.7 * (successes / total) + 0.3 * ((successes + 2) / (total + 4))), 3)

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("SELECT * FROM skills WHERE skill_id=?", (skill_id,)).fetchone()
        return self._skill_row(row) if row else None

    def list_skills(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM skills" + (" WHERE status=?" if status else "") + " ORDER BY confidence DESC"
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(query, (status,) if status else ()).fetchall()
        return [self._skill_row(row) for row in rows]

    @staticmethod
    def _skill_row(row: tuple) -> Dict[str, Any]:
        keys = ("skill_id", "created_at", "updated_at", "skill_name", "intent", "target", "phrase_patterns", "action_strategy", "expected_state", "success_count", "failure_count", "confidence", "status", "last_used", "last_verified")
        data = dict(zip(keys, row))
        for key, default in (("phrase_patterns", []), ("action_strategy", []), ("expected_state", {})):
            try: data[key] = json.loads(data[key] or "")
            except (TypeError, json.JSONDecodeError): data[key] = default
        return data

    def _event(self, skill_id: str, event_type: str, details: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("INSERT INTO skill_events VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4())[:16], datetime.now().isoformat(), skill_id, event_type, json.dumps(details, default=str)))
