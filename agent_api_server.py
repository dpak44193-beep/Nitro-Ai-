"""
AI CYBERSECURITY AGENT - REST API SERVER
Demonstrates: Real-world agent deployment with HTTP interface
"""

from fastapi import FastAPI, HTTPException, Header, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import json
import os
from datetime import datetime

# Import from core agent
from ai_agent_core import (
    SecureAIAgent, Tool, Permission,
    setup_example_agent
)
from desktop_agent import LocalInstructionAgent
from unified_execution_core import UnifiedExecutionCore

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ToolCallRequest(BaseModel):
    tool_id: str
    input_data: Dict
    reason: Optional[str] = None
    urgency: Optional[str] = "normal"  # normal, high, critical

class ToolCallResponse(BaseModel):
    status: str
    tool_id: str
    authorized: bool
    result: Dict
    timestamp: str
    agent_decision_reason: Optional[str] = None

class PermissionRequest(BaseModel):
    resource: str
    permission: str

class AuditQueryResponse(BaseModel):
    total_events: int
    events: List[Dict]

class AgentStatusResponse(BaseModel):
    agent_id: str
    agent_name: str
    is_active: bool
    credentials_valid: bool
    available_tools: int
    granted_permissions: Dict
    recent_audit_events: int

class DesktopInstructionRequest(BaseModel):
    instruction: str
    allow_desktop_control: bool = True
    dry_run: bool = False
    agent_id: str = "local_desktop_agent_001"
    access_token: str = "local-desktop-agent-token"
    consent: bool = True

class UnifiedActionRequest(BaseModel):
    action: str
    input_data: Dict = {}
    context: Dict = {}
    dry_run: bool = False

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="AI Cybersecurity Agent API",
    description="Secure AI agent with authorization, audit logging, and policy enforcement",
    version="1.0.0"
)

# Initialize agents
agent = setup_example_agent()
desktop_agent = LocalInstructionAgent(allow_desktop_control=True)
unified_core = UnifiedExecutionCore(
    "unified_local_agent_001",
    "Unified Local Desktop Agent",
    "local_user",
    desktop_agent=desktop_agent,
)
unified_core.grant_local_consent()
for _action in ("take_screenshot", "click_at", "type_text", "open_app", "press_key", "search_web"):
    unified_core.grant_permission(_action, "execute")
unified_core.add_policy({
    "agent_id": "unified_local_agent_001",
    "max_blast_radius": "medium",
    "allows_critical": False,
})

# ============================================================================
# MIDDLEWARE - REQUEST VALIDATION
# ============================================================================

@app.middleware("http")
async def validate_authentication(request, call_next):
    """Validate agent authentication on every request"""
    if request.url.path.startswith("/docs") or request.url.path.startswith("/openapi"):
        return await call_next(request)
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"error": "Missing or invalid Authorization header"}
        )
    
    token = auth_header.split("Bearer ")[1]
    authenticated = agent.authenticator.authenticate(agent.identity.agent_id, token)
    if not authenticated:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or expired credentials"}
        )
    
    return await call_next(request)

# ============================================================================
# CORE ENDPOINTS
# ============================================================================

@app.post("/api/v1/tools/call", response_model=ToolCallResponse)
async def call_tool(
    request: ToolCallRequest,
    authorization: str = Header(None)
):
    """
    Call a tool with full authorization chain
    
    Chain: Identity → Permission → Context → Policy → Authorization → Execute → Audit
    """
    
    try:
        # Extract token from header
        token = authorization.split("Bearer ")[1] if authorization else None
        
        # Call secure tool with authorization
        result = agent.call_tool(request.tool_id, request.input_data)
        
        tool = agent.tool_registry.get_tool(request.tool_id)
        blast_radius = tool.blast_radius if tool else "unknown"
        
        return ToolCallResponse(
            status=result.get("status", "UNKNOWN"),
            tool_id=request.tool_id,
            authorized=result.get("status") == "SUCCESS",
            result=result,
            timestamp=datetime.now().isoformat(),
            agent_decision_reason=result.get("error", result.get("message"))
        )
    
    except Exception as e:
        agent.audit.log_event("TOOL_CALL_ERROR", agent.identity.agent_id, 
                            "CALL", request.tool_id, False, details=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/agent/status", response_model=AgentStatusResponse)
async def get_agent_status():
    """Get agent operational status"""
    
    available_tools = agent.tool_registry.list_available_tools(agent.identity)
    
    return AgentStatusResponse(
        agent_id=agent.identity.agent_id,
        agent_name=agent.identity.agent_name,
        is_active=agent.identity.is_valid(),
        credentials_valid=agent.identity.is_valid(),
        available_tools=len(available_tools),
        granted_permissions={
            resource: [p.value for p in perms]
            for resource, perms in agent.identity.permissions.items()
        },
        recent_audit_events=len(agent.get_audit_trail()[-10:])
    )

@app.get("/api/v1/tools/available")
async def list_available_tools():
    """List tools agent can access"""
    
    available_tools = agent.tool_registry.list_available_tools(agent.identity)
    
    return {
        "total_available": len(available_tools),
        "tools": [
            {
                "tool_id": tool.tool_id,
                "name": tool.name,
                "description": tool.description,
                "blast_radius": tool.blast_radius,
                "permissions_required": [p.value for p in tool.required_permissions]
            }
            for tool in available_tools
        ]
    }

@app.get("/api/v1/audit/trail")
async def get_audit_trail(limit: int = 50):
    """Get audit trail"""
    
    events = agent.get_audit_trail()[:limit]
    
    return AuditQueryResponse(
        total_events=len(events),
        events=events
    )

@app.get("/api/v1/audit/by-event-type/{event_type}")
async def get_audit_by_type(event_type: str):
    """Filter audit by event type"""
    
    all_events = agent.get_audit_trail()
    filtered = [e for e in all_events if e["event_type"] == event_type]
    
    return {
        "event_type": event_type,
        "count": len(filtered),
        "events": filtered
    }

@app.get("/api/v1/audit/by-resource/{resource}")
async def get_audit_by_resource(resource: str):
    """Get all actions on specific resource"""
    
    all_events = agent.get_audit_trail()
    filtered = [e for e in all_events if e["resource"] == resource]
    
    return {
        "resource": resource,
        "total_actions": len(filtered),
        "allowed": len([e for e in filtered if e["permission_granted"]]),
        "denied": len([e for e in filtered if not e["permission_granted"]]),
        "events": filtered
    }

@app.post("/api/v1/memory/store")
async def store_memory(
    key: str = Body(...),
    value: str = Body(...),
    trust_level: str = Body("untrusted")
):
    """Store secure memory"""
    
    try:
        agent.memory.store(key, value, agent.identity.agent_id, trust_level)
        return {
            "status": "stored",
            "key": key,
            "trust_level": trust_level,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/memory/retrieve/{key}")
async def retrieve_memory(key: str):
    """Retrieve secure memory with trust level"""
    
    value = agent.memory.retrieve(key, agent.identity)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Memory key {key} not found")
    
    return {
        "key": key,
        "value": value,
        "trust_level": agent.memory.get_trust_level(key),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/context/add")
async def add_context(
    doc_id: str = Body(...),
    content: str = Body(...),
    source: str = Body(...),
    verified: bool = Body(False)
):
    """Add document to agent context"""
    
    agent.context.add_document(doc_id, content, source, verified)
    
    return {
        "status": "added",
        "doc_id": doc_id,
        "verified": verified,
        "source": source
    }

@app.get("/api/v1/context/validate/{doc_id}")
async def validate_context_document(doc_id: str):
    """Validate document integrity"""
    
    is_valid = agent.context.validate_document(doc_id)
    
    return {
        "doc_id": doc_id,
        "is_valid": is_valid,
        "status": "valid" if is_valid else "tampered_or_missing"
    }

@app.post("/api/v1/policy/add")
async def add_policy(policy: Dict):
    """Add authorization policy"""
    
    agent.add_policy(policy)
    
    return {
        "status": "added",
        "policy": policy,
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# DEMO ENDPOINTS
# ============================================================================

@app.get("/api/v1/demo/authorization-scenarios")
async def demo_authorization_scenarios():
    """Run all authorization test scenarios"""
    
    scenarios = []
    
    # Scenario 1: Allowed - Low blast radius
    result1 = agent.call_tool("scan_vulnerabilities", {"target": "192.168.1.0/24"})
    scenarios.append({
        "scenario": "ALLOWED - Low blast radius",
        "tool": "scan_vulnerabilities",
        "result": result1.get("status"),
        "reason": result1.get("error") or result1.get("message")
    })
    
    # Scenario 2: Allowed - Medium blast radius
    result2 = agent.call_tool("isolate_endpoint", {"endpoint_id": "SERVER_001"})
    scenarios.append({
        "scenario": "ALLOWED - Medium blast radius",
        "tool": "isolate_endpoint",
        "result": result2.get("status"),
        "reason": result2.get("error") or result2.get("message")
    })
    
    # Scenario 3: Denied - No admin permission
    result3 = agent.call_tool("kill_process", {"process_id": "12345"})
    scenarios.append({
        "scenario": "DENIED - Insufficient permissions",
        "tool": "kill_process",
        "result": result3.get("status"),
        "reason": result3.get("error") or result3.get("message")
    })
    
    # Scenario 4: Denied - Critical action blocked by policy
    result4 = agent.call_tool("network_shutdown", {"reason": "emergency"})
    scenarios.append({
        "scenario": "DENIED - Critical action (policy violation)",
        "tool": "network_shutdown",
        "result": result4.get("status"),
        "reason": result4.get("error") or result4.get("message")
    })
    
    return {
        "total_scenarios": len(scenarios),
        "scenarios": scenarios,
        "audit_events": len(agent.get_audit_trail())
    }

@app.get("/api/v1/demo/get-token")
async def demo_get_token():
    """Demo endpoint: Get agent credentials"""
    
    return {
        "agent_id": agent.identity.agent_id,
        "agent_name": agent.identity.agent_name,
        "token": agent.identity.credential_token,
        "expires_at": agent.identity.expiry.isoformat(),
        "usage": "Add 'Authorization: Bearer <token>' header to all requests"
    }

@app.get("/api/v1/desktop/status")
async def desktop_status():
    """Get desktop automation status for the local laptop permission model."""
    return {
        **desktop_agent.get_status(),
        "assigned_agent_id": desktop_agent.agent_id,
        "access_mode": "full_local_laptop_mode_with_permission_guard",
        "local_consent": True,
    }

@app.post("/api/v1/desktop/execute")
async def execute_desktop_instruction(payload: DesktopInstructionRequest):
    """Execute a local desktop instruction only for the assigned agent identity."""
    return desktop_agent.execute_instruction(
        payload.instruction,
        allow_desktop_control=payload.allow_desktop_control,
        dry_run=payload.dry_run,
        agent_id=payload.agent_id,
        access_token=payload.access_token,
        consent=payload.consent,
    )

@app.post("/api/v1/desktop/screenshot")
async def desktop_screenshot(payload: Dict = Body({"filename": "screen.png", "dry_run": False})):
    """Capture a screen snapshot from the local machine."""
    filename = payload.get("filename", "screen.png")
    dry_run = bool(payload.get("dry_run", False))
    return desktop_agent.take_screenshot(filename=filename, dry_run=dry_run)

@app.post("/api/v1/desktop/vision")
async def desktop_vision(payload: Dict = Body({"filename": "screen.png"})):
    """Inspect a screenshot with a basic vision-layer adapter."""
    filename = payload.get("filename", "screen.png")
    if not filename:
        filename = "screen.png"
    path = os.path.join(desktop_agent.capture_dir, filename)
    return desktop_agent.analyze_screen(path)

@app.get("/api/v1/unified/status")
async def unified_status():
    """Return the unified pipeline status and configured permissions."""
    return {
        "agent_id": unified_core.identity.agent_id,
        "agent_name": unified_core.identity.agent_name,
        "local_consent": unified_core.identity.local_consent,
        "admin_mode": unified_core.identity.admin_mode,
        "permissions": unified_core.identity.permissions,
        "execution_count": len(unified_core.get_execution_history()),
        "audit_event_count": len(unified_core.get_audit_trail()),
        "pipeline": [
            "authentication", "authorization", "validation", "execution",
            "observation", "verification", "memory_store", "recovery",
        ],
    }

@app.post("/api/v1/unified/execute")
async def execute_unified_action(payload: UnifiedActionRequest):
    """Execute one action through permission, observation and verification phases."""
    return await unified_core.execute_action(
        payload.action,
        payload.input_data,
        context=payload.context,
        dry_run=payload.dry_run,
    )

@app.get("/api/v1/unified/audit")
async def unified_audit():
    """Return the unified execution audit trail."""
    return {"events": unified_core.get_audit_trail()}

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent_active": agent.identity.is_valid(),
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with documentation"""
    return {
        "name": "AI Cybersecurity Agent API",
        "version": "1.0.0",
        "documentation": "/docs",
        "quick_start": {
            "1_get_credentials": "/api/v1/demo/get-token",
            "2_run_demo": "/api/v1/demo/authorization-scenarios",
            "3_check_audit": "/api/v1/audit/trail",
            "4_list_tools": "/api/v1/tools/available"
        }
    }

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print("AI CYBERSECURITY AGENT - REST API SERVER")
    print("=" * 80)
    print("\n📋 START SEQUENCE:")
    print("  1. Agent initialized with secure identity")
    print("  2. Tools registered with blast radius controls")
    print("  3. Permissions granted using least-privilege principle")
    print("  4. Audit logging configured")
    print("  5. Policy engine ready")
    print("\n🚀 SERVER STARTING...")
    print("   API Documentation: http://localhost:8000/docs")
    print("   Quick Start: http://localhost:8000/")
    print("   Get Token: http://localhost:8000/api/v1/demo/get-token")
    print("=" * 80 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
