# 🔒 AI CYBERSECURITY AGENT - COMPLETE IMPLEMENTATION

A production-grade AI security agent demonstrating secure architecture for autonomous systems with:
- **Identity & Authentication**: Agent credentials with token-based access
- **Authorization & IAM**: Role-based access control with least-privilege principle
- **Tool Security**: Secure tool calling with blast radius controls
- **Memory Management**: Secure memory with integrity checks and provenance
- **Audit Logging**: Complete audit trail of all actions
- **Policy Engine**: Authorization decisions with policy enforcement
- **Resource Monitoring**: CPU, memory tracking with limits
- **Change Tracking & Rollback**: Reverse execution effects if needed

---

## 📁 PROJECT STRUCTURE

```
.
├── ai_agent_core.py              # Core agent engine with IAM, tools, memory
├── agent_api_server.py           # FastAPI REST API for agent
├── tool_security_sandbox.py      # Safe tool execution with monitoring
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## 🎯 WHAT EACH FILE DOES

### 1. **ai_agent_core.py** - Core Agent Engine

The heart of the security agent.

**Components:**

| Component | Purpose |
|-----------|---------|
| `AgentIdentity` | Agent credentials, permissions, expiry |
| `AgentAuthenticator` | Authenticate agent credentials |
| `Tool` | Secure tool definition with blast radius |
| `ToolRegistry` | Register and manage tools |
| `SecureMemory` | Agent memory with integrity checks |
| `SecureContext` | Context management with source validation |
| `AuditLog` | SQLite audit database |
| `PolicyEngine` | Authorization decision engine |
| `SecureAIAgent` | Main orchestrator |

**Key Features:**

- **Identity Chain**: User → Agent → Permission → Tool → Data
- **Blast Radius**: Tools categorized as low/medium/high/critical
- **Least Privilege**: Each agent gets minimum required permissions
- **Authorization Flow**:
  ```
  Authenticate → Check Permission → Validate Context → 
  Evaluate Policy → Authorization Decision → Execute → Audit
  ```

**Run it:**
```bash
python ai_agent_core.py
```

Output shows:
- ✓ Allowed tool calls (low/medium blast radius)
- ✗ Denied tool calls (insufficient permissions)
- ✗ Denied tool calls (policy violation)
- Complete audit trail

---

### 2. **agent_api_server.py** - REST API

Expose the agent as HTTP API with automatic request validation.

**Key Endpoints:**

```
Authentication:
  GET /api/v1/demo/get-token
    → Returns agent credentials for Bearer token

Agent Status:
  GET /api/v1/agent/status
    → Agent operational status

Tool Management:
  POST /api/v1/tools/call
    → Call tool with authorization
  
  GET /api/v1/tools/available
    → List available tools

Audit Trail:
  GET /api/v1/audit/trail
    → Get audit events
  
  GET /api/v1/audit/by-event-type/{type}
    → Filter by event type
  
  GET /api/v1/audit/by-resource/{resource}
    → Filter by resource

Memory:
  POST /api/v1/memory/store
    → Store secure memory
  
  GET /api/v1/memory/retrieve/{key}
    → Retrieve memory

Context:
  POST /api/v1/context/add
    → Add document to context
  
  GET /api/v1/context/validate/{doc_id}
    → Validate document integrity

Demo:
  GET /api/v1/demo/authorization-scenarios
    → Run all authorization tests
```

**Middleware:**

- Automatic Bearer token validation
- Credential expiry checks
- Request/response logging

**Run it:**
```bash
python agent_api_server.py
```

Server starts at: `http://localhost:8000`
- Documentation: `/docs` (interactive Swagger UI)
- Quick start: `/`

---

### 3. **tool_security_sandbox.py** - Safe Tool Execution

Execute tools safely with containment and monitoring.

**Components:**

| Component | Purpose |
|-----------|---------|
| `ToolExecutionContext` | Complete execution lifecycle tracking |
| `InputValidator` | Prevent injection attacks |
| `ResourceMonitor` | Track CPU, memory during execution |
| `ChangeTracker` | Log all modifications |
| `SecureToolExecutor` | Main executor with full lifecycle |

**Execution Lifecycle:**

```
1. Create context
2. Validate input → Detect injection patterns
3. Sanitize input → Remove dangerous characters
4. Start monitoring → Resource tracking
5. Initialize change tracking
6. Execute tool
7. Stop monitoring → Resource stats
8. Check limits → Enforce resource caps
9. Verify changes → Record modifications
10. Generate audit
```

**Rollback Capability:**

- Track all changes: file creation, modification, API calls
- Generate rollback plan in reverse order
- Revert most recent first

**Run it:**
```bash
python tool_security_sandbox.py
```

Output shows:
- Execution with resource monitoring
- Changes tracked and rollback generated
- Complete execution report

---

## 🚀 QUICK START

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Run Core Agent Demo

```bash
python ai_agent_core.py
```

**Output:**
```
Test 1: Call allowed tool (scan_vulnerabilities - LOW blast radius)
Result: {"status": "SUCCESS", ...}

Test 2: Call allowed tool (isolate_endpoint - MEDIUM blast radius)
Result: {"status": "SUCCESS", ...}

Test 3: Call tool with insufficient permission (kill_process - HIGH)
Result: {"status": "DENIED", "error": "insufficient_permissions", ...}

Test 4: Call tool beyond policy scope (network_shutdown - CRITICAL)
Result: {"status": "DENIED", "error": "critical_action_requires_approval", ...}

AUDIT TRAIL
[timestamps] AUTHENTICATION agent_001 authenticated
[timestamps] TOOL_EXECUTION successful tool calls recorded
...
```

### Step 3: Start API Server

```bash
python agent_api_server.py
```

**Output:**
```
INFO:     Started server process [12345]
INFO:     Listening on 0.0.0.0:8000
```

### Step 4: Test API

**In another terminal:**

```bash
# Get agent credentials
curl http://localhost:8000/api/v1/demo/get-token

# Response:
{
  "agent_id": "agent_001",
  "agent_name": "CyberSecurity Analyst",
  "token": "abc123...",
  "usage": "Add 'Authorization: Bearer <token>' header to all requests"
}
```

```bash
# Run authorization scenarios
curl -H "Authorization: Bearer abc123..." \
  http://localhost:8000/api/v1/demo/authorization-scenarios

# Response shows allowed/denied decisions
```

```bash
# Check audit trail
curl -H "Authorization: Bearer abc123..." \
  http://localhost:8000/api/v1/audit/trail
```

### Step 5: Run Tool Security Sandbox

```bash
python tool_security_sandbox.py
```

**Output:**
```
TEST 1: Secure Tool Execution with Monitoring
Execution ID: a1b2c3d4...
Status: completed
Output: {...}
Changes made: 1
Events logged: 8

TEST 2: Execution with Change Tracking and Rollback
Changes made: 2
  Changes:
    - api_call: https://infra.api/isolate
    - file_create: /var/log/isolation_001.log
  
  Requesting rollback...
  Rollback plan: 2 actions
    - reverse_api_call: https://infra.api/isolate
    - delete_file: /var/log/isolation_001.log
```

---

## 🔐 SECURITY ARCHITECTURE FLOW

```
HUMAN REQUEST
     ↓
AGENT RECEIVES
     ↓
AUTHENTICATION (Identity)
  ✓ Credential valid?
  ✓ Not expired?
     ↓
AUTHORIZATION (Permissions)
  ✓ Agent has permission on resource?
  ✓ Tool required permission present?
     ↓
CONTEXT VALIDATION
  ✓ Context source verified?
  ✓ Documents not tampered?
     ↓
POLICY ENGINE
  ✓ Policy allows this action?
  ✓ Blast radius acceptable?
  ✓ Risk level approved?
     ↓
RESOURCE CHECK
  ✓ Memory available?
  ✓ CPU available?
  ✓ Timeout sufficient?
     ↓
EXECUTE WITH MONITORING
  ✓ Track changes
  ✓ Monitor resources
  ✓ Log events
     ↓
VERIFICATION
  ✓ Completed successfully?
  ✓ Resource limits respected?
  ✓ Expected outputs received?
     ↓
AUDIT RECORD
  ✓ Log all events
  ✓ Record decision rationale
  ✓ Store changes for rollback
     ↓
RESPONSE TO HUMAN
  ✓ Decision made
  ✓ Execution status
  ✓ Next steps if needed
```

---

## 📊 KEY CONCEPTS DEMONSTRATED

### 1. Identity & Authentication

```python
# Agent has credentials that must be valid
agent.identity.credential_token  # SHA256 hash of identity
agent.identity.expiry            # Token expiration date
agent.identity.is_valid()        # Check if still valid
```

**Security**: Tokens expire, credentials validated before any action.

### 2. Authorization (IAM)

```python
# Agent permissions are per-resource
agent.identity.grant_permission("scan_tool", Permission.EXECUTE)
agent.identity.has_permission("scan_tool", Permission.EXECUTE)  # True
agent.identity.has_permission("scan_tool", Permission.ADMIN)    # False
```

**Security**: Least privilege - agent only gets necessary permissions.

### 3. Tool Blast Radius

```python
tool1 = Tool("scan", "Scanner", "Scan system", blast_radius="low")
tool2 = Tool("isolate", "Isolator", "Isolate endpoint", blast_radius="medium")
tool3 = Tool("shutdown", "Shutdown", "Emergency stop", blast_radius="critical")
```

**Security**: Critical tools have stricter policy requirements.

### 4. Policy Engine

```python
# Policy can restrict critical actions even with permission
policy = {"agent_id": "agent_001", "allows_critical": False}
agent.add_policy(policy)

# Now tool.blast_radius = "critical" → DENIED
```

**Security**: Human-defined policies override raw permissions.

### 5. Audit Trail

```python
# Every action is logged
agent.audit.log_event("TOOL_EXECUTION", agent_id, "CALL", tool_id, True)

# Query later
events = agent.get_audit_trail()
```

**Security**: Complete record for forensics and compliance.

### 6. Secure Memory

```python
# Memory has trust levels and integrity checks
agent.memory.store("secret", "value", owner="agent_001", trust_level="trusted")
value = agent.memory.retrieve("secret", agent)  # With access log
trust = agent.memory.get_trust_level("secret")  # "trusted"
```

**Security**: Memory integrity verified, access logged, trust tracked.

### 7. Context Validation

```python
# Documents tracked with hash
agent.context.add_document("doc1", "content", "source", verified=True)

# Later check if tampered
is_valid = agent.context.validate_document("doc1")
```

**Security**: Detect if documents modified after ingestion.

### 8. Resource Monitoring

```python
# Monitor resource usage during execution
monitor = ResourceMonitor({"memory_mb": 512, "cpu_percent": 75})
monitor.start_monitoring()
# ... tool executes ...
stats = monitor.stop_monitoring()

# Get resource usage
print(stats["memory"]["max_mb"])
print(stats["cpu"]["max_percent"])
```

**Security**: Detect resource exhaustion attacks.

### 9. Change Tracking

```python
# Track all modifications
change_tracker.track_file_creation("/path/to/file", "content")
change_tracker.track_api_call("https://api.com/endpoint", "POST", data)

# Generate rollback if needed
rollback_plan = change_tracker.rollback_all()
```

**Security**: Reverse execution if it goes wrong.

### 10. Input Validation

```python
# Prevent injection attacks
InputValidator.validate_command(user_input)

# Results:
# - Command contains ";" → False (shell injection)
# - File path contains ".." → False (directory traversal)
# - Safe input → True
```

**Security**: Block malicious input patterns.

---

## 📈 AUTHORIZATION DECISION MATRIX

| Scenario | Permission | Policy | Blast Radius | Decision |
|----------|-----------|--------|--------------|----------|
| Low-risk scan | ✓ Has permission | Allows | LOW | **ALLOW** |
| Endpoint isolation | ✓ Has permission | Allows | MEDIUM | **ALLOW** |
| High-risk process kill | ✗ No admin | Allows | HIGH | **DENY** |
| Critical network stop | ✗ No permission | Blocks critical | CRITICAL | **DENY** |
| Memory poisoning attempt | ✓ Has permission | Blocks untrusted | - | **DENY** |

---

## 🧪 TESTING SCENARIOS

### Scenario 1: Least Privilege Success

Agent has minimal permissions → can only call low-risk tools → denied on higher-risk tools.

```bash
python ai_agent_core.py
# Test 1 & 2: ALLOWED ✓
# Test 3 & 4: DENIED ✓
```

### Scenario 2: Policy Enforcement

Same agent with policy → policy blocks critical actions even with permission.

```python
agent.add_policy({"agent_id": "agent_001", "allows_critical": False})
agent.call_tool("network_shutdown", {})  # DENIED by policy
```

### Scenario 3: Audit Trail Forensics

Track what happened and why.

```bash
curl http://localhost:8000/api/v1/audit/trail
# See: authentication, authorization decisions, tool calls, decisions rationale
```

### Scenario 4: Rollback on Error

Execute changes, then reverse them if needed.

```bash
python tool_security_sandbox.py
# Test 2 shows rollback plan generation
```

---

## 🛠️ EXTENDING THE AGENT

### Add New Tool

```python
# In ai_agent_core.py

tool = Tool("my_tool_id", "My Tool", "Tool description", "medium")
tool.add_required_permission(Permission.EXECUTE)
agent.register_tool(tool)
agent.grant_permission("my_tool_id", Permission.EXECUTE)
```

### Add New Permission

```python
# Tool now requires this permission
tool.add_required_permission(Permission.ADMIN)

# Grant to agent
agent.grant_permission("resource_id", Permission.ADMIN)
```

### Add New Policy

```python
policy = {
    "agent_id": "agent_001",
    "max_blast_radius": "high",
    "requires_approval": ["critical"],
    "allowed_tools": ["scan", "isolate"]
}
agent.add_policy(policy)
```

### Monitor Custom Resource

```python
from tool_security_sandbox import ResourceMonitor

monitor = ResourceMonitor({"memory_mb": 1024, "network_requests": 100})
monitor.start_monitoring()
# ... execution ...
stats = monitor.stop_monitoring()
```

---

## 📋 DEPLOYMENT CHECKLIST

- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Core agent runs successfully (`python ai_agent_core.py`)
- [ ] API server starts (`python agent_api_server.py`)
- [ ] Token generation works (`GET /api/v1/demo/get-token`)
- [ ] Tool calls authorized correctly (`POST /api/v1/tools/call`)
- [ ] Audit trail populated (`GET /api/v1/audit/trail`)
- [ ] Sandbox executes tools (`python tool_security_sandbox.py`)
- [ ] Rollback generation works (tool_security_sandbox.py Test 2)
- [ ] Memory operations functional (`POST /api/v1/memory/store`)
- [ ] Context validation active (`GET /api/v1/context/validate/{doc_id}`)

---

## 🔍 TROUBLESHOOTING

**Issue**: "ModuleNotFoundError: No module named 'fastapi'"
```bash
pip install -r requirements.txt
```

**Issue**: "Port 8000 already in use"
```bash
# Use different port
python -c "import agent_api_server; agent_api_server.app.run(port=8001)"
```

**Issue**: "Database locked" (audit.db)
```bash
# Delete old database
rm audit.db

# Run again
python ai_agent_core.py
```

**Issue**: Token validation fails
```bash
# Get new token
curl http://localhost:8000/api/v1/demo/get-token

# Use in requests
curl -H "Authorization: Bearer <NEW_TOKEN>" ...
```

---

## 📚 LEARNING PATH

1. **Start**: Read this README
2. **Core**: Run `python ai_agent_core.py` - See authorization in action
3. **API**: Run `python agent_api_server.py` - Test via REST
4. **Sandbox**: Run `python tool_security_sandbox.py` - See monitoring/rollback
5. **Extend**: Add custom tools/policies
6. **Deploy**: Use in production with proper configuration

---

## 🎯 CONCEPTS FROM ROADMAP

This implementation demonstrates:

✅ **2026 - Foundation**
- AI asset identity (AgentIdentity)
- Governance (PolicyEngine)
- AI-BOM (Agent components tracked)

✅ **2027 - Agentic Security**
- Agent Identity & IAM
- Authentication & Authorization
- Least Privilege

✅ **2028 - Defend Against Attacks**
- Tool Abuse prevention
- Input Validation/Sanitization
- Memory integrity

✅ **2029 - Autonomous SOC**
- Tool authorization decisions
- Blast radius controls
- Policy enforcement

✅ **2030 - Resilience**
- Change tracking & rollback
- Resource monitoring
- Complete audit trail

---

## 📞 SUPPORT

For issues or questions:

1. Check audit logs: `GET /api/v1/audit/trail`
2. Review execution reports: `tool_security_sandbox.py` output
3. Check event logs in core agent runs
4. Validate tool configuration
5. Verify permissions granted

---

## 📄 LICENSE

Educational implementation for AI Cybersecurity learning.

**Last Updated**: September 23, 2026

---

## 🚀 NEXT STEPS

1. **Integrate with real LLM**: Replace mock tool functions with actual Claude API calls
2. **Add multi-agent coordination**: Agent-to-agent authentication and authorization
3. **Implement MCP security**: Model Context Protocol tool integration
4. **Deploy to production**: Use in actual cybersecurity workflows
5. **Add ML-based detection**: Anomaly detection on execution patterns

