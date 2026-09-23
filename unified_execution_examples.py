"""Runnable examples for UnifiedExecutionCore."""

import asyncio

from unified_execution_core import UnifiedExecutionCore


def configured_core(agent_id: str = "example_001") -> UnifiedExecutionCore:
    core = UnifiedExecutionCore(agent_id, "Example Agent", "local_user")
    core.grant_local_consent()
    for action in ("take_screenshot", "open_app", "type_text", "click_at", "press_key", "search_web"):
        core.grant_permission(action, "execute")
    core.add_policy({"agent_id": agent_id, "max_blast_radius": "medium"})
    return core


async def example_dry_run() -> dict:
    core = configured_core()
    return await core.execute_action(
        "open_app", {"app": "notepad"},
        context={"blast_radius": "low"}, dry_run=True,
    )


async def example_real_workflow() -> list[dict]:
    core = configured_core("workflow_001")
    workflow = [
        ("open_app", {"app": "notepad"}),
        ("type_text", {"text": "Hello from the unified execution core"}),
        ("press_key", {"key": "enter"}),
    ]
    results = []
    for action, data in workflow:
        results.append(await core.execute_action(action, data, context={"blast_radius": "low"}))
    return results


async def example_permission_denied() -> dict:
    core = configured_core("restricted_001")
    return await core.execute_action(
        "shutdown", {}, context={"blast_radius": "critical"}, dry_run=False,
    )


async def main() -> None:
    print("Dry run:", await example_dry_run())
    print("Denied action:", await example_permission_denied())
    print("Audit events:", len(configured_core().get_audit_trail()))


if __name__ == "__main__":
    asyncio.run(main())
