"""Unified permission, desktop execution, observation, verification, memory and recovery core."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from action_schema import ActionTool
from desktop_agent import LocalInstructionAgent
from recovery_engine import RecoveryEngine
from tanglish_nlp import IntentActionMapper, TanglishNormalizer


class ExecutionPhase(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    EXECUTION = "execution"
    OBSERVATION = "observation"
    VERIFICATION = "verification"
    MEMORY_STORE = "memory_store"
    RECOVERY = "recovery"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionType(str, Enum):
    DESKTOP_CONTROL = "desktop_control"
    VOICE_INPUT = "voice_input"
    QUERY = "query"


class UnifiedIdentity:
    def __init__(self, agent_id: str, agent_name: str, owner: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.owner = owner
        self.created_at = datetime.now()
        self.expiry = datetime.now() + timedelta(days=365)
        self.permissions: Dict[str, List[str]] = {}
        self.local_consent = False
        self.admin_mode = False

    def grant_permission(self, resource: str, permission: str) -> None:
        self.permissions.setdefault(resource, [])
        if permission not in self.permissions[resource]:
            self.permissions[resource].append(permission)

    def has_permission(self, resource: str, permission: str) -> bool:
        permissions = self.permissions.get(resource, [])
        return permission in permissions or "admin" in permissions

    def is_valid(self) -> bool:
        return datetime.now() < self.expiry


class PermissionGuard:
    RESTRICTED_ACTIONS = {
        "shutdown", "restart", "delete_system_file", "kill_process",
        "install_software", "modify_registry", "network_disable",
        "browser_clear_data", "drop_database", "network_shutdown",
    }
    BLAST_LEVELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def __init__(self):
        self.policies: List[Dict[str, Any]] = []

    def add_policy(self, policy: Dict[str, Any]) -> None:
        self.policies.append(policy)

    def evaluate(self, identity: UnifiedIdentity, action: str, context: Dict[str, Any]) -> Tuple[bool, str, str]:
        blast_radius = context.get("blast_radius", "low")
        if not identity.is_valid():
            return False, "credential_expired", "critical"
        if not identity.has_permission(action, "execute"):
            return False, "insufficient_permissions", blast_radius
        if action.lower() in self.RESTRICTED_ACTIONS and not identity.admin_mode:
            return False, "restricted_action_requires_admin", "critical"
        if context.get("action_type") == ActionType.DESKTOP_CONTROL.value and not identity.local_consent:
            return False, "requires_local_consent", "medium"
        for policy in self.policies:
            if policy.get("agent_id") != identity.agent_id:
                continue
            maximum = policy.get("max_blast_radius", "medium")
            if self.BLAST_LEVELS.get(blast_radius, 0) > self.BLAST_LEVELS.get(maximum, 0):
                return False, "action_exceeds_policy_limit", blast_radius
            allowed = policy.get("allowed_actions")
            if allowed is not None and action not in allowed:
                return False, "action_not_allowed_by_policy", blast_radius
        return True, "authorized", blast_radius


class UnifiedMemory:
    def __init__(self, db_path: str = "unified_memory.db"):
        self.db_path = db_path
        self.memory: Dict[str, Dict[str, Any]] = {}
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS memory_store (
                    id TEXT PRIMARY KEY, key TEXT UNIQUE, value TEXT, owner TEXT,
                    trust_level TEXT, value_hash TEXT, created_at TEXT, expires_at TEXT
                )
            """)

    def store(self, key: str, value: str, owner: str, trust_level: str = "untrusted") -> None:
        created = datetime.now()
        expires = created + timedelta(days=7)
        entry = {
            "id": str(uuid.uuid4()), "key": key, "value": value, "owner": owner,
            "trust_level": trust_level, "value_hash": hashlib.sha256(value.encode()).hexdigest(),
            "created_at": created.isoformat(), "expires_at": expires.isoformat(),
        }
        self.memory[key] = entry
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO memory_store VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(entry.values()),
            )

    def retrieve(self, key: str) -> Optional[str]:
        entry = self.memory.get(key)
        if entry is None:
            return None
        if datetime.fromisoformat(entry["expires_at"]) < datetime.now():
            self.memory.pop(key, None)
            return None
        return entry["value"]


class UnifiedAuditLog:
    def __init__(self, db_path: str = "unified_audit.db"):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY, timestamp TEXT, agent_id TEXT, phase TEXT,
                    action TEXT, status TEXT, blast_radius TEXT, input_hash TEXT,
                    output_hash TEXT, details TEXT
                )
            """)

    def log(self, agent_id: str, phase: str, action: str, status: str,
            blast_radius: str = "low", input_data: Any = None,
            output_data: Any = None, details: str = "") -> None:
        def digest(value: Any) -> str:
            return hashlib.sha256(json.dumps(value or {}, sort_keys=True, default=str).encode()).hexdigest()

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), datetime.now().isoformat(), agent_id, phase, action,
                 status, blast_radius, digest(input_data), digest(output_data), details),
            )

    def get_trail(self, agent_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT id, timestamp, agent_id, phase, action, status, blast_radius, details "
                "FROM audit_log WHERE agent_id = ? ORDER BY timestamp DESC", (agent_id,)
            ).fetchall()
        return [dict(zip(("id", "timestamp", "agent_id", "phase", "action", "status", "blast_radius", "details"), row)) for row in rows]


class Observer:
    def __init__(self):
        self.observations: List[Dict[str, Any]] = []

    async def observe(self, result: Dict[str, Any], action: str) -> Dict[str, Any]:
        observation = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "status": result.get("status"),
            "is_anomaly": result.get("status") not in {"completed", "dry_run"},
            "details": result,
        }
        self.observations.append(observation)
        return observation


class Verifier:
    async def verify(self, result: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        expected_status = expected.get("status")
        actual_status = result.get("status")
        if expected_status and actual_status != expected_status:
            return False, "status_mismatch", {"expected": expected_status, "actual": actual_status}
        if result.get("error"):
            return False, "execution_error", {"error": result["error"]}
        return True, "verified", {"verified_at": datetime.now().isoformat()}


class UnifiedExecutionCore:
    """Single guarded pipeline backed by the existing real desktop executor."""

    def __init__(self, agent_id: str, agent_name: str, owner: str, desktop_agent: Optional[LocalInstructionAgent] = None):
        self.identity = UnifiedIdentity(agent_id, agent_name, owner)
        self.permission_guard = PermissionGuard()
        self.desktop_agent = desktop_agent or LocalInstructionAgent(allow_desktop_control=True)
        self.observer = Observer()
        self.verifier = Verifier()
        self.memory = UnifiedMemory()
        self.audit = UnifiedAuditLog()
        self.recovery = RecoveryEngine(self.desktop_agent)
        self.execution_history: Dict[str, Dict[str, Any]] = {}

    async def execute_action(self, action: str, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        execution_id = str(uuid.uuid4())[:16]
        context = dict(context or {})
        context.setdefault("action_type", ActionType.DESKTOP_CONTROL.value)
        context.setdefault("blast_radius", "low")
        self.audit.log(self.identity.agent_id, ExecutionPhase.AUTHENTICATION.value, action, "checking", input_data=input_data)
        try:
            allowed, reason, blast = self.permission_guard.evaluate(self.identity, action, context)
            if not allowed:
                return self._response(execution_id, "denied", reason, ExecutionPhase.AUTHORIZATION, blast)
            if not isinstance(input_data, dict):
                return self._response(execution_id, "denied", "input_must_be_dict", ExecutionPhase.VALIDATION, blast)

            self.audit.log(self.identity.agent_id, ExecutionPhase.EXECUTION.value, action, "executing", blast, input_data)
            instruction = self._action_to_instruction(action, input_data)
            if instruction is None:
                return self._response(execution_id, "failed", f"unsupported_action: {action}", ExecutionPhase.VALIDATION, blast)
            before_screen = None
            expected = context.get("expected_outcome") or {}
            if not dry_run and not expected:
                return self._response(execution_id, "failed", "expected_state_required", ExecutionPhase.VALIDATION, blast)
            has_real_expectation = any(key in expected for key in ("window", "text", "screen_changed"))
            if not dry_run and not has_real_expectation:
                return self._response(execution_id, "failed", "real_expected_state_required", ExecutionPhase.VALIDATION, blast)
            if not dry_run and has_real_expectation:
                before_screen = self.desktop_agent.observer.screenshot("before")

            result = self.desktop_agent.execute_instruction(instruction, allow_desktop_control=True, dry_run=dry_run, consent=True)
            if not dry_run and has_real_expectation:
                real_verification = self.desktop_agent.verify_action(
                    result,
                    expected,
                    before_screen,
                    timeout=context.get("verification_timeout", 10.0),
                )
                observation = await self.observer.observe(real_verification.get("action", result), action)
                if real_verification.get("status") != "VERIFIED":
                    failure_reason = real_verification.get("verification", {}).get("reason", "real_observer_failed")
                    recovery = self.recovery.recover(action, input_data, expected, failure_reason, execution_id, dry_run)
                    return self._recovery_response(execution_id, action, input_data, result, recovery, blast, real_verification)
            else:
                observation = await self.observer.observe(result, action)
            if observation["is_anomaly"]:
                failure_reason = result.get("error", "action_not_completed")
                recovery = self.recovery.recover(action, input_data, expected, failure_reason, execution_id, dry_run)
                return self._recovery_response(execution_id, action, input_data, result, recovery, blast, result)

            verified, verify_reason, verification = await self.verifier.verify(result, expected)
            if not verified:
                recovery = self.recovery.recover(action, input_data, expected, verify_reason, execution_id, dry_run)
                return self._recovery_response(execution_id, action, input_data, result, recovery, blast, result)

            memory_key = f"execution:{execution_id}:{action}"
            self.memory.store(memory_key, json.dumps(result, default=str), self.identity.agent_id, "trusted")
            self.audit.log(self.identity.agent_id, ExecutionPhase.COMPLETED.value, action, "completed", blast, input_data, result)
            self.execution_history[execution_id] = {"execution_id": execution_id, "action": action, "result": result, "observation": observation, "verification": verification}
            return self._response(execution_id, "completed", "success", ExecutionPhase.COMPLETED, blast, data=result)
        except Exception as exc:
            return self._response(execution_id, "failed", str(exc), ExecutionPhase.FAILED, context["blast_radius"])

    def _recovery_response(
        self,
        execution_id: str,
        action: str,
        input_data: Dict[str, Any],
        result: Dict[str, Any],
        recovery: Dict[str, Any],
        blast: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        if recovery.get("recovered"):
            self.audit.log(
                self.identity.agent_id,
                ExecutionPhase.RECOVERY.value,
                action,
                "recovered",
                blast,
                input_data,
                recovery,
            )
            memory_key = f"execution:{execution_id}:{action}"
            self.memory.store(
                memory_key,
                json.dumps(recovery, default=str),
                self.identity.agent_id,
                "verified",
            )
            self.execution_history[execution_id] = {
                "execution_id": execution_id,
                "action": action,
                "result": result,
                "recovery": recovery,
                "status": "recovered",
            }
            return self._response(
                execution_id,
                "completed",
                "action_recovered",
                ExecutionPhase.RECOVERY,
                blast,
                data=recovery,
                recovery=recovery,
            )

        return self._response(
            execution_id,
            "failed",
            recovery.get("message", "recovery_failed"),
            ExecutionPhase.FAILED,
            blast,
            data=data,
            recovery=recovery,
        )

    async def execute_tool(self, tool: ActionTool, dry_run: bool = False) -> Dict[str, Any]:
        """Execute a schema-defined action with verification-aware retries."""
        validation = tool.validate()
        if not validation["valid"]:
            return {"status": "failed", "message": validation["reason"]}

        action_map = {
            "OPEN_APP": "open_app",
            "TYPE_TEXT": "type_text",
            "CLICK": "click_at",
            "OPEN_URL": "open_url",
        }
        action = action_map.get(tool.action_id)
        if action is None:
            return {"status": "failed", "message": f"unsupported_action: {tool.action_id}"}

        last_result: Dict[str, Any] = {}
        attempts = tool.retry_policy.max_retries + 1
        for attempt in range(attempts):
            context = {
                "blast_radius": tool.metadata.get("blast_radius", "low"),
                "risk_level": tool.risk_level,
                "expected_outcome": tool.expected_state.to_dict(),
                "verification_timeout": tool.timeout,
                "retry_attempt": attempt,
            }
            last_result = await self.execute_action(action, tool.parameters, context=context, dry_run=dry_run)
            if last_result.get("status") in {"completed", "dry_run"}:
                last_result.setdefault("data", {})
                last_result["data"]["action_tool"] = tool.to_dict()
                return last_result
            if attempt < attempts - 1:
                import asyncio
                await asyncio.sleep(tool.retry_policy.retry_delay)
        return last_result

    async def execute_user_command(self, user_input: str, dry_run: bool = False) -> Dict[str, Any]:
        """Normalize a user command, then execute it through the guarded core."""
        normalizer = getattr(self.desktop_agent, "tanglish_nlp", None)
        normalizer = normalizer or TanglishNormalizer()
        intent = normalizer.normalize(user_input)
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

        result = await self.execute_action(
            mapped["action"],
            mapped["input_data"],
            context={"expected_outcome": mapped["expected_outcome"]},
            dry_run=dry_run,
        )
        result["intent"] = intent
        return result

    @staticmethod
    def _action_to_instruction(action: str, data: Dict[str, Any]) -> Optional[str]:
        if action == "take_screenshot":
            return "take screenshot"
        if action == "click_at":
            return f"click at {data.get('x')} {data.get('y')}"
        if action == "type_text":
            return f"type {data.get('text', '')}"
        if action == "open_app":
            return f"open {data.get('app', '')}"
        if action == "press_key":
            return f"press {data.get('key', '')}"
        if action == "search_web":
            return f"search web {data.get('query', '')}"
        if action == "open_url":
            return f"open url {data.get('url', '')}"
        return None

    def _response(self, execution_id: str, status: str, message: str, phase: ExecutionPhase, blast: str, data: Optional[Dict[str, Any]] = None, recovery: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = {"execution_id": execution_id, "status": status, "message": message, "phase": phase.value, "blast_radius": blast, "timestamp": datetime.now().isoformat()}
        if data is not None:
            response["data"] = data
        if recovery is not None:
            response["recovery"] = recovery
        return response

    def grant_permission(self, resource: str, permission: str) -> None:
        self.identity.grant_permission(resource, permission)

    def grant_local_consent(self) -> None:
        self.identity.local_consent = True

    def grant_admin_mode(self) -> None:
        self.identity.admin_mode = True

    def add_policy(self, policy: Dict[str, Any]) -> None:
        self.permission_guard.add_policy(policy)

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        return self.audit.get_trail(self.identity.agent_id)

    def get_execution_history(self) -> List[Dict[str, Any]]:
        return list(self.execution_history.values())
