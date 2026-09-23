# 🤖 INTEGRATION GUIDE - Claude AI Integration

This guide shows how to connect your AI Cybersecurity Agent to Claude API to make it a real LLM-powered autonomous agent.

---

## 📊 ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                     USER REQUEST                             │
│              "Scan network for vulnerabilities"              │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   AGENT INTERFACE                            │
│            (Authentication, Authorization)                   │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                  CLAUDE LLM API                              │
│        (Reasoning, decision-making, tool selection)          │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              TOOL AUTHORIZATION LAYER                        │
│    (Permission check, policy evaluation, blast radius)       │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│            SECURE TOOL EXECUTION SANDBOX                     │
│  (Input validation, monitoring, change tracking, rollback)   │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                 ACTUAL TOOLS                                 │
│      (Vulnerability scanner, endpoint isolator, etc.)        │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                    RESULTS                                   │
│              (Audit logged, rollback enabled)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 STEP 1: Install Claude SDK

```bash
pip install anthropic
```

---

## 🔧 STEP 2: Create Claude-Integrated Agent

Create file: `claude_agent.py`

```python
"""
AI Agent with Claude API Integration
Combines security controls with Claude's reasoning
"""

from anthropic import Anthropic
from ai_agent_core import SecureAIAgent, Tool, Permission
import json

class ClaudeSecurityAgent:
    """Agent combining Claude API with security controls"""
    
    def __init__(self, agent_id: str, agent_name: str, owner: str, api_key: str):
        # Initialize security agent
        self.security_agent = SecureAIAgent(agent_id, agent_name, owner)
        
        # Initialize Claude client
        self.claude = Anthropic(api_key=api_key)
        self.conversation_history = []
        
    def register_tools(self, tools: list):
        """Register tools with security agent"""
        for tool in tools:
            self.security_agent.register_tool(tool)
    
    def grant_permissions(self, permissions: dict):
        """Grant permissions to agent"""
        for resource, perms in permissions.items():
            for perm in perms:
                self.security_agent.grant_permission(resource, perm)
    
    def add_policy(self, policy: dict):
        """Add authorization policy"""
        self.security_agent.add_policy(policy)
    
    def process_request(self, user_message: str) -> str:
        """
        Process user request through Claude with security controls
        
        Flow:
        1. User request
        2. Claude reasons about what to do
        3. Claude selects tool
        4. Security layer authorizes tool
        5. Tool executes securely
        6. Results back to Claude
        7. Claude analyzes and responds
        """
        
        # Add to conversation
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Get available tools
        available_tools = self.security_agent.tool_registry.list_available_tools(
            self.security_agent.identity
        )
        
        # Format tools for Claude
        tools_for_claude = self._format_tools_for_claude(available_tools)
        
        # Call Claude with tools
        response = self.claude.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=self._get_system_prompt(),
            tools=tools_for_claude,
            messages=self.conversation_history
        )
        
        # Process Claude's response
        result = self._process_claude_response(response, tools_for_claude)
        
        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": result["message"]
        })
        
        return result["message"]
    
    def _get_system_prompt(self) -> str:
        """System prompt for Claude"""
        return """You are a Cybersecurity Analyst AI Agent.

Your responsibilities:
1. Analyze security threats and vulnerabilities
2. Recommend appropriate security actions
3. Use available tools to gather information and take action
4. Always consider the blast radius (impact) of your actions
5. Explain your reasoning and decisions

Important constraints:
- You can only use tools explicitly provided
- Some tools have high blast radius and require special approval
- Always prefer non-destructive actions (scanning vs isolating)
- Gather information before taking action
- Ask for human confirmation before critical actions

Available tools are described below. Use them when appropriate."""
    
    def _format_tools_for_claude(self, tools: list) -> list:
        """Format tools for Claude API"""
        claude_tools = []
        
        for tool in tools:
            claude_tools.append({
                "name": tool.tool_id,
                "description": f"{tool.description} (Blast radius: {tool.blast_radius})",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target for the tool"
                        },
                        "options": {
                            "type": "object",
                            "description": "Additional options"
                        }
                    },
                    "required": ["target"]
                }
            })
        
        return claude_tools
    
    def _process_claude_response(self, response, tools_for_claude: list) -> dict:
        """Process Claude's response and execute tools if needed"""
        
        result_message = ""
        tool_results = []
        
        for block in response.content:
            if hasattr(block, 'text'):
                result_message += block.text
            
            elif block.type == "tool_use":
                # Claude wants to use a tool
                tool_name = block.name
                tool_input = block.input
                
                # Authorize tool call through security agent
                auth_result = self.security_agent.call_tool(tool_name, tool_input)
                
                # Format tool result for Claude
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(auth_result)
                })
                
                result_message += f"\n[Tool: {tool_name} - Status: {auth_result.get('status')}]"
        
        # If tools were used, get Claude's analysis
        if tool_results:
            # Continue conversation with tool results
            self.conversation_history.append({
                "role": "assistant",
                "content": response.content
            })
            
            self.conversation_history.append({
                "role": "user",
                "content": tool_results
            })
            
            # Get Claude's analysis of tool results
            analysis_response = self.claude.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                system=self._get_system_prompt(),
                messages=self.conversation_history
            )
            
            analysis_message = ""
            for block in analysis_response.content:
                if hasattr(block, 'text'):
                    analysis_message += block.text
            
            result_message += f"\n{analysis_message}"
        
        return {
            "message": result_message,
            "tool_calls": len(tool_results)
        }

# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def example_claude_integration():
    """Demonstrate Claude-integrated agent"""
    
    import os
    
    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Set ANTHROPIC_API_KEY environment variable")
    
    # Create agent
    agent = ClaudeSecurityAgent(
        agent_id="claude_security_001",
        agent_name="Claude Security Analyst",
        owner="security_team",
        api_key=api_key
    )
    
    # Register tools
    tools = [
        Tool("scan_vulnerabilities", "Vulnerability Scanner", 
             "Scan for security vulnerabilities", "low"),
        Tool("query_logs", "Log Query", 
             "Query security logs", "low"),
        Tool("isolate_endpoint", "Endpoint Isolation", 
             "Isolate compromised endpoint", "medium"),
    ]
    
    for tool in tools:
        tool.add_required_permission(Permission.EXECUTE)
        agent.register_tools([tool])
    
    # Grant permissions
    agent.grant_permissions({
        "scan_vulnerabilities": [Permission.EXECUTE],
        "query_logs": [Permission.EXECUTE],
        "isolate_endpoint": [Permission.EXECUTE]
    })
    
    # Add policy
    agent.add_policy({
        "agent_id": "claude_security_001",
        "max_blast_radius": "medium"
    })
    
    # Example conversation
    print("=" * 80)
    print("CLAUDE-INTEGRATED SECURITY AGENT")
    print("=" * 80)
    
    # Request 1: Reconnaissance
    print("\n📋 REQUEST 1: Initial reconnaissance")
    print("-" * 80)
    response = agent.process_request(
        "Scan the network 192.168.1.0/24 for vulnerabilities"
    )
    print(f"Agent: {response}")
    
    # Request 2: Investigation
    print("\n📋 REQUEST 2: Investigate findings")
    print("-" * 80)
    response = agent.process_request(
        "Check the logs for any suspicious activity on SERVER_001"
    )
    print(f"Agent: {response}")
    
    # Request 3: Remediation consideration
    print("\n📋 REQUEST 3: Remediation options")
    print("-" * 80)
    response = agent.process_request(
        "If SERVER_001 is compromised, what should we do? Can you help isolate it?"
    )
    print(f"Agent: {response}")
    
    # Audit trail
    print("\n📋 AUDIT TRAIL")
    print("-" * 80)
    for event in agent.security_agent.get_audit_trail()[:5]:
        print(f"{event['timestamp']} | {event['event_type']}")
        print(f"  → {event['action']} on {event['resource']}")
        print(f"  → Authorized: {event['permission_granted']}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    example_claude_integration()
```

---

## 🔧 STEP 3: Environment Setup

Create `.env` file:

```env
# Claude API Configuration
ANTHROPIC_API_KEY=sk-ant-...your-api-key-here...

# Agent Configuration
AGENT_ID=claude_security_001
AGENT_NAME=Claude Security Analyst
AGENT_OWNER=security_team

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Security Configuration
MAX_BLAST_RADIUS=medium
ALLOW_CRITICAL_ACTIONS=false

# Audit Configuration
AUDIT_DB_PATH=./audit.db
AUDIT_RETENTION_DAYS=90
```

Load with:

```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
agent_id = os.getenv("AGENT_ID")
```

---

## 🔧 STEP 4: Run Claude-Integrated Agent

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run agent
python claude_agent.py
```

Output:

```
================================================================================
CLAUDE-INTEGRATED SECURITY AGENT
================================================================================

📋 REQUEST 1: Initial reconnaissance
────────────────────────────────────────────────────────────────────────────
Agent: I'll scan the network 192.168.1.0/24 for vulnerabilities...
[Tool: scan_vulnerabilities - Status: SUCCESS]

Based on the scan results, I found several potential vulnerabilities:
- Open SSH ports on multiple hosts
- Outdated TLS version on web servers
- Unpatched systems requiring updates

Recommendation: Prioritize patching the critical vulnerabilities...

📋 REQUEST 2: Investigate findings
────────────────────────────────────────────────────────────────────────────
Agent: Checking logs on SERVER_001...
[Tool: query_logs - Status: SUCCESS]

The logs show suspicious login attempts around 03:45 UTC. 
This correlates with the vulnerability scan findings...

📋 AUDIT TRAIL
────────────────────────────────────────────────────────────────────────────
2024-01-15T10:30:45Z | TOOL_EXECUTION
  → EXECUTE scan_vulnerabilities
  → Authorized: true
```

---

## 🎯 MULTI-TURN CONVERSATION FLOW

```
User: "Check if server X is compromised"
  ↓
Claude reasons: "I should scan logs and check for indicators of compromise"
  ↓
Claude decides: "Use query_logs tool"
  ↓
Security layer: "Permission check... ALLOWED"
  ↓
Tool executes: Returns logs with suspicious activity
  ↓
Claude analyzes: "Found 50 failed logins in 10 minutes - likely compromised"
  ↓
Claude recommends: "Recommend isolating SERVER_001"
  ↓
User: "Do it, isolate the server"
  ↓
Claude decides: "Use isolate_endpoint tool"
  ↓
Security layer: "Permission check... ALLOWED (medium blast radius)"
  ↓
Tool executes: Server isolated from network
  ↓
Claude reports: "Server isolated. Running follow-up scan..."
  ↓
Complete audit trail of all decisions
```

---

## 🔐 TOOL DEFINITION FORMAT

When registering tools with Claude:

```python
Tool(
    tool_id="identify_in_claude",
    name="Human-readable name",
    description="What tool does (Claude will read this)",
    blast_radius="low|medium|high|critical"
)
```

Claude can see:
- ✓ Tool name and description
- ✓ Input schema (what parameters it accepts)
- ✓ Blast radius (impact level)

Claude cannot see:
- ✗ Actual permissions required
- ✗ Authorization policy
- ✗ Implementation details
- ✗ Memory/security internals

---

## 🛡️ SECURITY LAYERS

```
Claude's Tool Decision
        ↓
Security Agent intercepts
        ↓
Layer 1: Authentication
  → Is agent credential valid?
        ↓
Layer 2: Authorization
  → Does agent have permission?
        ↓
Layer 3: Policy
  → Does policy allow this?
        ↓
Layer 4: Context
  → Is context source trusted?
        ↓
Layer 5: Resource
  → Are resources available?
        ↓
Layer 6: Input Validation
  → Is input safe/not injection?
        ↓
Execute Tool
        ↓
Layer 7: Resource Monitoring
  → Memory/CPU within limits?
        ↓
Layer 8: Change Tracking
  → Record all modifications
        ↓
Layer 9: Audit
  → Log complete decision rationale
        ↓
Return Result to Claude
```

Claude never knows about layers 2-9. It only sees:
- Tool available or not
- Tool executed or failed
- Result of execution

---

## 📊 EXAMPLE: Multi-Step Incident Response

```
User: "There's been a data breach. Investigate and contain it."

Claude: "I'll help with the incident response. Let me start by:
1. Querying the logs to understand what happened
2. Identifying the compromised systems
3. Isolating them to prevent further damage"

Step 1: SCAN LOGS
  → Security: AUTHORIZED (read-only, low blast radius)
  → Result: Breach detected at 02:15 UTC, affected systems: SERVER_A, SERVER_B

Step 2: ANALYZE
  → Claude: "Found root cause - unpatched RCE vulnerability"
  → Claude: "Affected systems need immediate isolation"

Step 3: ISOLATE ENDPOINT 1
  → User asks: "Isolate SERVER_A?"
  → Security: AUTHORIZED (medium blast radius, policy allows)
  → Result: SERVER_A isolated from network

Step 4: ISOLATE ENDPOINT 2
  → User asks: "Isolate SERVER_B?"
  → Security: AUTHORIZED (medium blast radius, policy allows)
  → Result: SERVER_B isolated from network

Step 5: FINAL REPORT
  → Claude: "Incident contained. Changes made and logged.
    If needed, we can rollback the isolation.
    Recommend: Apply security patches before reconnecting."

AUDIT TRAIL:
  [10:30] Authentication OK
  [10:31] Tool: query_logs → AUTHORIZED → SUCCESS
  [10:32] Tool: isolate_endpoint SERVER_A → AUTHORIZED → SUCCESS
  [10:33] Tool: isolate_endpoint SERVER_B → AUTHORIZED → SUCCESS
  [10:35] All changes logged and reversible
```

---

## 🚀 PRODUCTION DEPLOYMENT

### Docker Container

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY *.py .

# Set environment
ENV PYTHONUNBUFFERED=1

# Run API server
CMD ["python", "agent_api_server.py"]
```

Build and run:

```bash
docker build -t ai-security-agent .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -e AGENT_ID="prod_agent_001" \
  ai-security-agent
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-security-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-security-agent
  template:
    metadata:
      labels:
        app: ai-security-agent
    spec:
      containers:
      - name: agent
        image: ai-security-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: claude-api
              key: key
        - name: AGENT_ID
          value: "prod_agent_001"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

---

## 🧪 TESTING

```python
# test_claude_agent.py

import pytest
from claude_agent import ClaudeSecurityAgent
from ai_agent_core import Tool, Permission

@pytest.fixture
def agent():
    return ClaudeSecurityAgent(
        "test_agent",
        "Test Agent",
        "test_team",
        "sk-ant-test-key"
    )

def test_tool_registration(agent):
    tool = Tool("test_tool", "Test", "Test tool", "low")
    agent.register_tools([tool])
    assert len(agent.security_agent.tool_registry.tools) == 1

def test_permission_granting(agent):
    agent.grant_permissions({
        "resource": [Permission.EXECUTE]
    })
    assert agent.security_agent.identity.has_permission(
        "resource", Permission.EXECUTE
    )

def test_policy_enforcement(agent):
    agent.add_policy({"allows_critical": False})
    assert agent.security_agent.policy_engine.policies[0]["allows_critical"] == False

# Run tests
# pytest test_claude_agent.py -v
```

---

## 📈 MONITORING

```python
# Monitor agent decisions

import time
from datetime import datetime

decisions = []

def log_decision(tool_id: str, authorized: bool, reason: str, duration: float):
    decisions.append({
        "timestamp": datetime.now().isoformat(),
        "tool": tool_id,
        "authorized": authorized,
        "reason": reason,
        "duration_ms": duration * 1000
    })

# Analyze patterns
authorized_rate = sum(1 for d in decisions if d["authorized"]) / len(decisions)
avg_duration = sum(d["duration_ms"] for d in decisions) / len(decisions)

print(f"Authorization rate: {authorized_rate * 100:.1f}%")
print(f"Average decision time: {avg_duration:.1f}ms")
```

---

## 🔗 NEXT INTEGRATION STEPS

1. **Add Real Tools**: Replace mock functions with actual API calls
2. **Multi-Agent**: Agents coordinating with each other
3. **MCP Integration**: Use Model Context Protocol for tool discovery
4. **Observability**: Connect to monitoring systems (Datadog, New Relic)
5. **Learning**: Improve decision-making from historical data
6. **Feedback**: Human-in-the-loop for controversial decisions

---

**Remember**: The security controls work regardless of whether Claude makes good decisions. Claude is the "brain" - security layers are the "guardrails."

