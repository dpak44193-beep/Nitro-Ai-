# 🎯 AI CYBERSECURITY AGENT - QUICK REFERENCE

## 🚀 30-Second Start

```bash
# Install
pip install -r requirements.txt

# Run core demo
python ai_agent_core.py

# Run API server
python agent_api_server.py

# Test in another terminal
curl http://localhost:8000/api/v1/demo/authorization-scenarios
```

---

## 📋 ARCHITECTURE AT A GLANCE

```
User Request
    ↓
Agent Identity (Authentication)
    ↓
Permission Check (Authorization)
    ↓
Policy Engine (Policy Enforcement)
    ↓
Tool Security Sandbox (Execution)
    ↓
Audit Logger (Recording)
```

---

## 🔑 KEY CONCEPTS

### 1. **Identity** (Who?)
- Agent has unique ID, credentials, expiry
- Every request authenticated first
- Tokens are time-limited

### 2. **Authorization** (What can do?)
- Per-resource permissions (READ, WRITE, EXECUTE, ADMIN)
- Least privilege principle - only minimum required
- Example: Agent can READ logs but not DELETE them

### 3. **Tool Blast Radius** (What's the impact?)
```
LOW       → Safe, limited impact, auto-allowed
MEDIUM    → Moderate impact, requires permission check
HIGH      → Significant impact, requires admin + policy
CRITICAL  → Business-critical, blocked by default
```

### 4. **Policy Engine** (Can we do this now?)
- Human-defined rules override raw permissions
- Example: "This agent cannot execute critical actions"
- Policy blocks even if agent has permission

### 5. **Audit Trail** (What happened?)
- Every decision logged: timestamp, actor, action, result, reason
- Enables forensics and compliance

### 6. **Tool Execution** (How to execute safely?)
1. Validate input (block injection)
2. Sanitize input (remove dangerous chars)
3. Monitor resources (CPU, memory limits)
4. Track changes (enable rollback)
5. Verify execution (check results)

---

## 🛠️ COMMON TASKS

### Create Agent

```python
from ai_agent_core import SecureAIAgent

agent = SecureAIAgent(
    agent_id="my_agent",
    agent_name="My Agent",
    owner="team"
)
```

### Register Tool

```python
from ai_agent_core import Tool, Permission

tool = Tool(
    tool_id="scan_tool",
    name="Vulnerability Scanner",
    description="Scan for vulnerabilities",
    blast_radius="low"
)

tool.add_required_permission(Permission.EXECUTE)
agent.register_tool(tool)
```

### Grant Permission

```python
agent.grant_permission("scan_tool", Permission.EXECUTE)
# Now agent can use scan_tool
```

### Call Tool (with full authorization)

```python
result = agent.call_tool("scan_tool", {"target": "192.168.1.0/24"})
# Result includes:
# - status: SUCCESS or DENIED
# - result: tool output or error message
# - audit: logged automatically
```

### Check Audit Trail

```python
events = agent.get_audit_trail()
for event in events:
    print(f"{event['timestamp']} | {event['event_type']}")
    print(f"  Agent: {event['agent_id']}")
    print(f"  Allowed: {event['permission_granted']}")
```

### Add Security Policy

```python
policy = {
    "agent_id": "my_agent",
    "allows_critical": False,
    "max_blast_radius": "high"
}
agent.add_policy(policy)
```

---

## 📊 AUTHORIZATION DECISION FLOW

```python
# This is what happens inside agent.call_tool()

# Step 1: Authenticate
if not agent.identity.is_valid():
    return DENIED  # Credential expired

# Step 2: Check Permission
if not agent.identity.has_permission("scan_tool", Permission.EXECUTE):
    return DENIED  # No permission

# Step 3: Get Tool
tool = tool_registry.get_tool("scan_tool")
if tool is None:
    return DENIED  # Tool not found

# Step 4: Evaluate Policy
authorized, reason = policy_engine.evaluate_authorization(agent, tool, context)
if not authorized:
    return DENIED  # Policy violation

# Step 5: Execute
result = execute_tool_securely(tool, input_data)

# Step 6: Audit
audit_log.log_event(
    event_type="TOOL_EXECUTION",
    agent_id=agent.identity.agent_id,
    action="EXECUTE",
    resource=tool.tool_id,
    authorized=True
)

return SUCCESS
```

---

## 🔌 REST API ENDPOINTS

### Get Token
```bash
curl http://localhost:8000/api/v1/demo/get-token
# Returns: agent_id, token, expiry
```

### Call Tool
```bash
curl -X POST http://localhost:8000/api/v1/tools/call \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "scan_vulnerabilities",
    "input_data": {"target": "192.168.1.0/24"}
  }'
```

### List Available Tools
```bash
curl http://localhost:8000/api/v1/tools/available \
  -H "Authorization: Bearer TOKEN"
```

### Get Audit Trail
```bash
curl http://localhost:8000/api/v1/audit/trail \
  -H "Authorization: Bearer TOKEN"
```

### Store Memory
```bash
curl -X POST http://localhost:8000/api/v1/memory/store \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "alert_threshold",
    "value": "70",
    "trust_level": "trusted"
  }'
```

### Retrieve Memory
```bash
curl http://localhost:8000/api/v1/memory/retrieve/alert_threshold \
  -H "Authorization: Bearer TOKEN"
```

### Run Demo
```bash
curl http://localhost:8000/api/v1/demo/authorization-scenarios \
  -H "Authorization: Bearer TOKEN"
```

---

## 💾 TOOL SECURITY SANDBOX

### Execute Tool Safely

```python
from tool_security_sandbox import SecureToolExecutor

executor = SecureToolExecutor()

ctx = executor.execute(
    tool_id="scan_tool",
    agent_id="agent_001",
    input_data={"target": "192.168.1.0/24"},
    tool_function=my_scan_function,
    resource_limits={
        "memory_mb": 512,
        "cpu_percent": 75,
        "timeout_seconds": 30
    }
)

print(f"Status: {ctx.state}")
print(f"Output: {ctx.output_data}")
print(f"Changes: {len(ctx.changes_made)}")
```

### Request Rollback

```python
rollback = executor.request_rollback(ctx.execution_id)
print(f"Rollback plan: {len(rollback['rollback_plan'])} actions")
for action in rollback['rollback_plan']:
    print(f"  - {action['action']}")
```

### Get Execution Report

```python
report = executor.get_execution_report(ctx.execution_id)
print(report["summary"])  # Status, duration, resource usage
print(report["events"])   # Event log
print(report["changes"])  # Modifications made
```

---

## 🔐 PERMISSION MODEL

### Available Permissions

```python
class Permission(Enum):
    READ = "read"           # Read data
    WRITE = "write"         # Modify data
    DELETE = "delete"       # Remove data
    EXECUTE = "execute"     # Run tool
    ADMIN = "admin"         # Administrative
```

### Grant Permission

```python
agent.grant_permission("resource_id", Permission.EXECUTE)
```

### Check Permission

```python
has_perm = agent.identity.has_permission("resource_id", Permission.EXECUTE)
```

---

## 📊 BLAST RADIUS MEANINGS

| Radius | Impact | Requirements | Example |
|--------|--------|--------------|---------|
| LOW | Limited | Execute permission | Vulnerability scan |
| MEDIUM | Moderate | Execute + Policy | Isolate endpoint |
| HIGH | Significant | Admin + Policy | Kill process |
| CRITICAL | Business-critical | Blocked by policy | Network shutdown |

---

## 🧪 TEST SCENARIOS

### Scenario 1: Permission Denied
```python
# Agent doesn't have admin permission
agent.call_tool("high_risk_tool", {})
# Result: DENIED - insufficient_permissions
```

### Scenario 2: Policy Violation
```python
# Tool is critical, policy blocks it
agent.call_tool("critical_tool", {})
# Result: DENIED - critical_action_requires_approval
```

### Scenario 3: Success
```python
# Agent has permission, policy allows, input valid
agent.call_tool("low_risk_tool", {"target": "192.168.1.0/24"})
# Result: SUCCESS
```

### Scenario 4: Expired Credentials
```python
# Agent credential token expired
agent.identity.expiry = datetime.now() - timedelta(days=1)
agent.call_tool("any_tool", {})
# Result: DENIED - agent_credential_expired
```

---

## 📈 MONITORING

### Check Agent Status

```python
print(f"Agent: {agent.identity.agent_name}")
print(f"Valid: {agent.identity.is_valid()}")
print(f"Permissions: {len(agent.identity.permissions)}")
print(f"Audit events: {len(agent.get_audit_trail())}")
```

### Check Tool Availability

```python
available_tools = agent.tool_registry.list_available_tools(agent.identity)
print(f"Available tools: {len(available_tools)}")
for tool in available_tools:
    print(f"  - {tool.name} ({tool.blast_radius})")
```

### Analyze Audit Trail

```python
events = agent.get_audit_trail()

# Count by type
tool_calls = len([e for e in events if e['event_type'] == 'TOOL_EXECUTION'])
denied = len([e for e in events if not e['permission_granted']])
print(f"Tool calls: {tool_calls}")
print(f"Denied: {denied}")
```

---

## ⚙️ CONFIGURATION

### Create Agent with Custom Config

```python
agent = SecureAIAgent("agent_001", "My Agent", "team")

# Customize permissions
agent.grant_permission("tool_a", Permission.EXECUTE)
agent.grant_permission("tool_b", Permission.EXECUTE)
agent.grant_permission("tool_c", Permission.READ)

# Customize policy
agent.add_policy({
    "agent_id": "agent_001",
    "max_blast_radius": "high",
    "allows_critical": False
})

# Add tools
tool = Tool("my_tool", "My Tool", "Description", "low")
agent.register_tool(tool)
```

---

## 🐛 DEBUGGING

### Check Why Tool Call Failed

```python
result = agent.call_tool("my_tool", {})
if result['status'] != 'SUCCESS':
    error = result.get('error')
    print(f"Error: {error}")
    # Possible errors:
    # - tool_not_found
    # - authentication_failed
    # - insufficient_permissions
    # - critical_action_requires_approval
    # - untrusted_context
```

### Review Audit for Specific Tool

```python
all_events = agent.get_audit_trail()
tool_events = [e for e in all_events if e['resource'] == 'my_tool']
for event in tool_events:
    print(f"{event['timestamp']} | Allowed: {event['permission_granted']}")
```

### Check Memory Integrity

```python
# Store memory
agent.memory.store("key", "value", agent.identity.agent_id, "trusted")

# Verify it's trusted
trust_level = agent.memory.get_trust_level("key")
print(f"Trust level: {trust_level}")  # "trusted"

# Retrieve with access logged
value = agent.memory.retrieve("key", agent.identity)
print(f"Value: {value}")
```

---

## 🚀 PRODUCTION CHECKLIST

- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Core agent runs: `python ai_agent_core.py`
- [ ] API server starts: `python agent_api_server.py`
- [ ] Token generation works
- [ ] Tool calls authorized correctly
- [ ] Audit trail populated
- [ ] Memory operations working
- [ ] Context validation active
- [ ] Rollback generation functional
- [ ] Error handling in place
- [ ] Logs being written
- [ ] Database persisting audit events
- [ ] API endpoints responding
- [ ] Documentation reviewed

---

## 📚 FILE REFERENCE

| File | Purpose |
|------|---------|
| `ai_agent_core.py` | Core agent with IAM, tools, memory |
| `agent_api_server.py` | REST API wrapper |
| `tool_security_sandbox.py` | Safe tool execution |
| `requirements.txt` | Python dependencies |
| `README.md` | Full documentation |
| `INTEGRATION_GUIDE.md` | Claude API integration |
| `QUICK_REFERENCE.md` | This file |

---

## 🆘 COMMON ERRORS

**Error**: "tool_not_found"
- Fix: Tool not registered. Call `agent.register_tool(tool)`

**Error**: "insufficient_permissions"
- Fix: Grant permission. Call `agent.grant_permission(resource, permission)`

**Error**: "critical_action_requires_approval"
- Fix: Update policy to allow. Call `agent.add_policy({...})`

**Error**: "agent_credential_expired"
- Fix: Create new agent. Old credential tokens expire after 365 days.

**Error**: "Port 8000 already in use"
- Fix: Use different port or kill existing process:
  ```bash
  lsof -i :8000
  kill -9 <PID>
  ```

---

## 📞 NEED HELP?

1. Read `README.md` for complete documentation
2. Read `INTEGRATION_GUIDE.md` for Claude API integration
3. Check audit trail: `GET /api/v1/audit/trail`
4. Review core agent: `python ai_agent_core.py`
5. Check API logs: Look at server output

---

**Last Updated**: September 23, 2026

**Status**: Production Ready ✓

