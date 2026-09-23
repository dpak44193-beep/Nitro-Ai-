# Unified Execution Core

`UnifiedExecutionCore` combines the existing permission, desktop execution, observation, verification, memory, recovery, and audit paths.

## Pipeline

```text
User action
  -> authentication
  -> authorization
  -> validation
  -> desktop execution
  -> observation
  -> verification
  -> memory store
  -> audit
  -> recovery on failure
```

## Migration

Old desktop usage:

```python
from desktop_agent import LocalInstructionAgent
agent = LocalInstructionAgent(allow_desktop_control=True)
agent.execute_instruction("open notepad then type hello")
```

Unified usage:

```python
from unified_execution_core import UnifiedExecutionCore

core = UnifiedExecutionCore("agent_001", "Desktop Agent", "local_user")
core.grant_local_consent()
core.grant_permission("open_app", "execute")
core.grant_permission("type_text", "execute")
core.add_policy({"agent_id": "agent_001", "max_blast_radius": "medium"})

result = await core.execute_action("open_app", {"app": "notepad"})
```

## API endpoints

With the API server running and a valid bearer token:

- `GET /api/v1/unified/status`
- `POST /api/v1/unified/execute`
- `GET /api/v1/unified/audit`

Example request:

```json
{
  "action": "type_text",
  "input_data": {"text": "hello"},
  "context": {"blast_radius": "low"},
  "dry_run": false
}
```

The core uses the existing `LocalInstructionAgent`, so existing app aliases, voice/overlay support, screenshots, and Tanglish planning remain available. Restricted system actions remain denied unless explicitly configured in admin mode.
