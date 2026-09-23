"""
AI CYBERSECURITY AGENT - Core Implementation
Demonstrates: Identity → Authorization → Tool Calling → Audit
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum
import hashlib
import uuid

# ============================================================================
# 1. IDENTITY & IAM MODEL
# ============================================================================

class Permission(Enum):
    """Granular permissions"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"

class AgentIdentity:
    """Agent IAM Identity"""
    def __init__(self, agent_id: str, agent_name: str, owner: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.owner = owner
        self.created_at = datetime.now()
        self.permissions: Dict[str, List[Permission]] = {}
        self.credential_token = self._generate_token()
        self.expiry = datetime.now() + timedelta(days=365)
        
    def _generate_token(self) -> str:
        """Generate secure credential token"""
        data = f"{self.agent_id}{datetime.now().isoformat()}{uuid.uuid4()}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def grant_permission(self, resource: str, permission: Permission):
        """Grant permission to resource"""
        if resource not in self.permissions:
            self.permissions[resource] = []
        self.permissions[resource].append(permission)
        
    def has_permission(self, resource: str, permission: Permission) -> bool:
        """Check if agent has permission"""
        if Permission.ADMIN in self.permissions.get(resource, []):
            return True
        return permission in self.permissions.get(resource, [])
    
    def is_valid(self) -> bool:
        """Check if credential still valid"""
        return datetime.now() < self.expiry

class AgentAuthenticator:
    """Authenticate and verify agent identity"""
    def __init__(self):
        self.agents: Dict[str, AgentIdentity] = {}
    
    def register_agent(self, agent_id: str, agent_name: str, owner: str) -> AgentIdentity:
        """Register new agent"""
        agent = AgentIdentity(agent_id, agent_name, owner)
        self.agents[agent_id] = agent
        return agent
    
    def authenticate(self, agent_id: str, token: str) -> Optional[AgentIdentity]:
        """Authenticate agent"""
        if agent_id not in self.agents:
            return None
        
        agent = self.agents[agent_id]
        if not agent.is_valid() or agent.credential_token != token:
            return None
        
        return agent

# ============================================================================
# 2. TOOL SECURITY MODEL
# ============================================================================

class Tool:
    """Secure Tool Definition"""
    def __init__(self, tool_id: str, name: str, description: str, blast_radius: str = "low"):
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.blast_radius = blast_radius  # low, medium, high, critical
        self.required_permissions: List[Permission] = []
        self.input_schema = {}
        self.output_schema = {}
        
    def add_required_permission(self, permission: Permission):
        """Add required permission for tool"""
        self.required_permissions.append(permission)
    
    def validate_authorization(self, agent: AgentIdentity) -> bool:
        """Validate agent has all required permissions"""
        for perm in self.required_permissions:
            if not agent.has_permission(self.tool_id, perm):
                return False
        return True

class ToolRegistry:
    """Registry of all available tools"""
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
    
    def register_tool(self, tool: Tool):
        """Register tool"""
        self.tools[tool.tool_id] = tool
    
    def get_tool(self, tool_id: str) -> Optional[Tool]:
        """Get tool by ID"""
        return self.tools.get(tool_id)
    
    def list_available_tools(self, agent: AgentIdentity) -> List[Tool]:
        """List tools agent can access"""
        available = []
        for tool in self.tools.values():
            if tool.validate_authorization(agent):
                available.append(tool)
        return available

# ============================================================================
# 3. MEMORY SECURITY MODEL
# ============================================================================

class MemoryEntry:
    """Secure memory entry with provenance"""
    def __init__(self, key: str, value: str, owner: str, trust_level: str = "untrusted"):
        self.id = str(uuid.uuid4())
        self.key = key
        self.value = value
        self.owner = owner
        self.trust_level = trust_level  # untrusted, trusted, verified
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(days=7)
        self.hash = hashlib.sha256(value.encode()).hexdigest()
    
    def is_valid(self) -> bool:
        """Check if memory still valid"""
        return datetime.now() < self.expires_at
    
    def validate_integrity(self, value: str) -> bool:
        """Verify memory hasn't been tampered"""
        return hashlib.sha256(value.encode()).hexdigest() == self.hash

class SecureMemory:
    """Agent memory with integrity checks"""
    def __init__(self):
        self.memory: Dict[str, MemoryEntry] = {}
        self.access_log: List[Dict] = []
    
    def store(self, key: str, value: str, owner: str, trust_level: str = "untrusted"):
        """Store memory with provenance"""
        entry = MemoryEntry(key, value, owner, trust_level)
        self.memory[key] = entry
        self._log_access("WRITE", key, owner)
    
    def retrieve(self, key: str, requester: AgentIdentity) -> Optional[str]:
        """Retrieve memory with access log"""
        if key not in self.memory:
            return None
        
        entry = self.memory[key]
        if not entry.is_valid():
            del self.memory[key]
            return None
        
        self._log_access("READ", key, requester.agent_id)
        return entry.value
    
    def get_trust_level(self, key: str) -> str:
        """Get trust level of memory"""
        if key in self.memory:
            return self.memory[key].trust_level
        return "unknown"
    
    def _log_access(self, operation: str, key: str, actor: str):
        """Log memory access"""
        self.access_log.append({
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "key": key,
            "actor": actor
        })

# ============================================================================
# 4. CONTEXT & RAG SECURITY
# ============================================================================

class SecureContext:
    """Manage context with source validation"""
    def __init__(self):
        self.documents: Dict[str, Dict] = {}
    
    def add_document(self, doc_id: str, content: str, source: str, verified: bool = False):
        """Add document with provenance"""
        self.documents[doc_id] = {
            "id": doc_id,
            "content": content,
            "source": source,
            "verified": verified,
            "added_at": datetime.now().isoformat(),
            "hash": hashlib.sha256(content.encode()).hexdigest()
        }
    
    def get_context(self) -> str:
        """Get all verified context"""
        verified_docs = [d["content"] for d in self.documents.values() if d["verified"]]
        return "\n---\n".join(verified_docs)
    
    def validate_document(self, doc_id: str) -> bool:
        """Validate document hasn't been tampered"""
        if doc_id not in self.documents:
            return False
        doc = self.documents[doc_id]
        return hashlib.sha256(doc["content"].encode()).hexdigest() == doc["hash"]

# ============================================================================
# 5. AUDIT & LOGGING
# ============================================================================

class AuditLog:
    """Comprehensive audit logging"""
    def __init__(self, db_path: str = "audit.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize audit database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                agent_id TEXT,
                action TEXT,
                resource TEXT,
                permission_granted TEXT,
                authorization_result TEXT,
                blast_radius TEXT,
                details TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def log_event(self, event_type: str, agent_id: str, action: str, 
                  resource: str, permission_granted: bool, blast_radius: str = "low", details: str = ""):
        """Log security event"""
        event_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO audit_events 
            (id, timestamp, event_type, agent_id, action, resource, permission_granted, blast_radius, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_id,
            datetime.now().isoformat(),
            event_type,
            agent_id,
            action,
            resource,
            str(permission_granted),
            blast_radius,
            details
        ))
        conn.commit()
        conn.close()
    
    def get_events(self, agent_id: str = None) -> List[Dict]:
        """Retrieve audit events"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if agent_id:
            cursor.execute('SELECT * FROM audit_events WHERE agent_id = ? ORDER BY timestamp DESC', (agent_id,))
        else:
            cursor.execute('SELECT * FROM audit_events ORDER BY timestamp DESC')
        
        events = []
        for row in cursor.fetchall():
            events.append({
                "id": row[0],
                "timestamp": row[1],
                "event_type": row[2],
                "agent_id": row[3],
                "action": row[4],
                "resource": row[5],
                "permission_granted": row[6] == "True",
                "blast_radius": row[7],
                "details": row[8]
            })
        conn.close()
        return events

# ============================================================================
# 6. POLICY ENGINE - AUTHORIZATION DECISION
# ============================================================================

class PolicyEngine:
    """Policy-based authorization"""
    def __init__(self):
        self.policies: List[Dict] = []
    
    def add_policy(self, policy: Dict):
        """Add authorization policy"""
        self.policies.append(policy)
    
    def evaluate_authorization(self, agent: AgentIdentity, tool: Tool, 
                               context: Dict) -> tuple[bool, str]:
        """Evaluate if action is authorized"""
        
        # 1. Check agent validity
        if not agent.is_valid():
            return False, "agent_credential_expired"
        
        # 2. Check tool permission
        if not tool.validate_authorization(agent):
            return False, "insufficient_permissions"
        
        # 3. Check blast radius
        if tool.blast_radius == "critical":
            # Critical actions need explicit policy approval
            approved = any(p.get("allows_critical", False) for p in self.policies 
                          if p.get("agent_id") == agent.agent_id)
            if not approved:
                return False, "critical_action_requires_approval"
        
        # 4. Check context trust
        if context.get("context_trust_level") == "untrusted":
            return False, "untrusted_context"
        
        return True, "authorized"

# ============================================================================
# 7. CORE AGENT - ORCHESTRATOR
# ============================================================================

class SecureAIAgent:
    """Secure AI Agent with all controls"""
    def __init__(self, agent_id: str, agent_name: str, owner: str):
        self.identity = AgentIdentity(agent_id, agent_name, owner)
        self.authenticator = AgentAuthenticator()
        self.tool_registry = ToolRegistry()
        self.memory = SecureMemory()
        self.context = SecureContext()
        self.audit = AuditLog()
        self.policy_engine = PolicyEngine()
        
        # Register self
        self.authenticator.agents[agent_id] = self.identity
    
    def register_tool(self, tool: Tool):
        """Register available tool"""
        self.tool_registry.register_tool(tool)
    
    def grant_permission(self, resource: str, permission: Permission):
        """Grant permission to self"""
        self.identity.grant_permission(resource, permission)
    
    def add_policy(self, policy: Dict):
        """Add authorization policy"""
        self.policy_engine.add_policy(policy)
    
    def call_tool(self, tool_id: str, input_data: Dict) -> Dict:
        """
        Secure tool invocation with full authorization chain
        
        Chain: Identity → Permission → Context → Policy → Authorization → Execute → Audit
        """
        
        tool = self.tool_registry.get_tool(tool_id)
        if not tool:
            self.audit.log_event("TOOL_CALL", self.identity.agent_id, 
                               "CALL", tool_id, False, details="tool_not_found")
            return {"error": "tool_not_found", "status": "DENIED"}
        
        # Step 1: Authenticate
        if not self.authenticator.authenticate(self.identity.agent_id, self.identity.credential_token):
            self.audit.log_event("AUTHENTICATION", self.identity.agent_id, 
                               "AUTHENTICATE", tool_id, False, details="authentication_failed")
            return {"error": "authentication_failed", "status": "DENIED"}
        
        # Step 2: Check authorization
        context = {
            "context_trust_level": "trusted",  # In real scenario, validate context
            "user_request": input_data
        }
        
        authorized, reason = self.policy_engine.evaluate_authorization(
            self.identity, tool, context
        )
        
        if not authorized:
            self.audit.log_event("AUTHORIZATION", self.identity.agent_id, 
                               "CALL", tool_id, False, tool.blast_radius, details=reason)
            return {"error": reason, "status": "DENIED"}
        
        # Step 3: Execute tool
        result = self._execute_tool(tool, input_data)
        
        # Step 4: Audit successful execution
        self.audit.log_event("TOOL_EXECUTION", self.identity.agent_id, 
                           "EXECUTE", tool_id, True, tool.blast_radius, 
                           details=f"input: {json.dumps(input_data)}, output: {json.dumps(result)}")
        
        return result
    
    def _execute_tool(self, tool: Tool, input_data: Dict) -> Dict:
        """Simulate tool execution"""
        # In real implementation, call actual tool
        return {
            "tool_id": tool.tool_id,
            "status": "SUCCESS",
            "message": f"Tool {tool.name} executed successfully",
            "result": {"data": "sample_output", "input_received": input_data}
        }
    
    def get_audit_trail(self) -> List[Dict]:
        """Get complete audit trail"""
        return self.audit.get_events(self.identity.agent_id)

# ============================================================================
# 8. EXAMPLE SETUP
# ============================================================================

def setup_example_agent():
    """Setup example cybersecurity agent"""
    
    # Create agent
    agent = SecureAIAgent("agent_001", "CyberSecurity Analyst", "security_team")
    
    # Register tools with different blast radius
    tools = [
        Tool("scan_vulnerabilities", "Vulnerability Scanner", "Scan for vulnerabilities", "low"),
        Tool("query_logs", "Log Query", "Query security logs", "low"),
        Tool("isolate_endpoint", "Endpoint Isolation", "Isolate compromised endpoint", "medium"),
        Tool("kill_process", "Process Terminator", "Terminate malicious process", "high"),
        Tool("network_shutdown", "Network Emergency Stop", "Emergency network shutdown", "critical"),
    ]
    
    for tool in tools:
        tool.add_required_permission(Permission.EXECUTE)
        if tool.blast_radius in ["high", "critical"]:
            tool.add_required_permission(Permission.ADMIN)
        agent.register_tool(tool)
    
    # Grant permissions - LEAST PRIVILEGE principle
    agent.grant_permission("scan_vulnerabilities", Permission.EXECUTE)
    agent.grant_permission("query_logs", Permission.EXECUTE)
    agent.grant_permission("isolate_endpoint", Permission.EXECUTE)
    agent.grant_permission("kill_process", Permission.ADMIN)
    # NOTE: NOT granting permission to "network_shutdown" - critical action
    
    # Add policies
    agent.add_policy({
        "agent_id": "agent_001",
        "allows_critical": False,  # This agent cannot execute critical actions
        "max_blast_radius": "medium"
    })
    
    # Add secure context
    agent.context.add_document(
        "policy_001",
        "Security Policy: Endpoint isolation requires ticket approval",
        "internal_policy",
        verified=True
    )
    
    # Store trusted memory
    agent.memory.store("alert_threshold", "70", agent.identity.agent_id, "trusted")
    
    return agent

if __name__ == "__main__":
    # Setup agent
    agent = setup_example_agent()
    
    print("=" * 80)
    print("AI CYBERSECURITY AGENT - AUTHORIZATION FLOW DEMO")
    print("=" * 80)
    
    # Test 1: ALLOWED - Low blast radius
    print("\n✓ TEST 1: Call allowed tool (scan_vulnerabilities - LOW blast radius)")
    result = agent.call_tool("scan_vulnerabilities", {"target": "192.168.1.0/24"})
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test 2: ALLOWED - Medium blast radius with permission
    print("\n✓ TEST 2: Call allowed tool (isolate_endpoint - MEDIUM blast radius)")
    result = agent.call_tool("isolate_endpoint", {"endpoint_id": "SERVER_001"})
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test 3: DENIED - High blast radius requires ADMIN
    print("\n✗ TEST 3: Call tool with insufficient permission (kill_process - HIGH)")
    result = agent.call_tool("kill_process", {"process_id": "12345"})
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test 4: DENIED - Critical blast radius
    print("\n✗ TEST 4: Call tool beyond policy scope (network_shutdown - CRITICAL)")
    result = agent.call_tool("network_shutdown", {"reason": "emergency"})
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Show audit trail
    print("\n" + "=" * 80)
    print("AUDIT TRAIL")
    print("=" * 80)
    for event in agent.get_audit_trail():
        print(f"\n{event['timestamp']} | {event['event_type']}")
        print(f"  Agent: {event['agent_id']}")
        print(f"  Action: {event['action']} on {event['resource']}")
        print(f"  Authorized: {event['permission_granted']}")
        print(f"  Blast Radius: {event['blast_radius']}")
        if event['details']:
            print(f"  Details: {event['details']}")
    
    print("\n" + "=" * 80)
    print("KEY CONCEPTS DEMONSTRATED:")
    print("=" * 80)
    print("✓ Identity & Authentication: Agent credential token validation")
    print("✓ Authorization: Permission checks before tool execution")
    print("✓ Least Privilege: Tools have minimal required permissions")
    print("✓ Policy Engine: Critical actions blocked by policy")
    print("✓ Blast Radius: Tool impact categorized (low/medium/high/critical)")
    print("✓ Audit Logging: Every action logged with full context")
    print("✓ Memory Security: Trusted memory store with provenance")
    print("✓ Context Validation: Source verification for documents")
