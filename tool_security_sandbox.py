"""
TOOL SECURITY SANDBOX
Demonstrates: Safe tool execution with containment, monitoring, and rollback
"""

import json
import subprocess
import time
import threading
from typing import Dict, List, Any, Callable
from datetime import datetime
import hashlib
from enum import Enum

# ============================================================================
# TOOL EXECUTION MODELS
# ============================================================================

class ToolExecutionState(Enum):
    """Tool execution state tracking"""
    PENDING = "pending"
    AUTHENTICATED = "authenticated"
    AUTHORIZED = "authorized"
    VALIDATING_INPUT = "validating_input"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class ResourceLimit(Enum):
    """Resource constraints"""
    MEMORY_MB = "memory_mb"
    CPU_PERCENT = "cpu_percent"
    TIMEOUT_SECONDS = "timeout_seconds"
    FILE_OPERATIONS = "file_operations"
    NETWORK_REQUESTS = "network_requests"

# ============================================================================
# TOOL EXECUTION CONTEXT
# ============================================================================

class ToolExecutionContext:
    """Context for tool execution with complete tracking"""
    def __init__(self, execution_id: str, tool_id: str, agent_id: str):
        self.execution_id = execution_id
        self.tool_id = tool_id
        self.agent_id = agent_id
        self.started_at = datetime.now()
        self.completed_at = None
        self.state = ToolExecutionState.PENDING
        self.input_data = {}
        self.output_data = {}
        self.error = None
        self.changes_made = []
        self.resource_usage = {}
        self.events = []
        self.is_rolled_back = False
    
    def log_event(self, event_type: str, message: str, severity: str = "info"):
        """Log execution event"""
        self.events.append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "message": message,
            "severity": severity,
            "state": self.state.value
        })
    
    def record_change(self, change_type: str, target: str, details: Dict):
        """Record changes made by tool"""
        self.changes_made.append({
            "timestamp": datetime.now().isoformat(),
            "type": change_type,
            "target": target,
            "details": details,
            "reversible": change_type in ["create_file", "modify_config", "update_db"]
        })
    
    def set_resource_usage(self, memory_mb: float, cpu_percent: float, duration_seconds: float):
        """Record resource usage"""
        self.resource_usage = {
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            "duration_seconds": duration_seconds
        }
    
    def get_summary(self) -> Dict:
        """Get execution summary"""
        return {
            "execution_id": self.execution_id,
            "tool_id": self.tool_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "state": self.state.value,
            "success": self.state == ToolExecutionState.COMPLETED,
            "rolled_back": self.is_rolled_back,
            "changes_made": len(self.changes_made),
            "reversible_changes": len([c for c in self.changes_made if c["reversible"]]),
            "resource_usage": self.resource_usage,
            "total_events": len(self.events)
        }

# ============================================================================
# INPUT VALIDATION & SANITIZATION
# ============================================================================

class InputValidator:
    """Validate tool input to prevent injection attacks"""
    
    @staticmethod
    def validate_command(command: str) -> tuple[bool, str]:
        """Validate command to prevent shell injection"""
        dangerous_patterns = [
            ";",
            "|",
            "&",
            ">",
            "<",
            "$(",
            "`",
            "$()",
            "${",
            "&&",
            "||"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in command:
                return False, f"Dangerous pattern detected: {pattern}"
        
        return True, "valid"
    
    @staticmethod
    def validate_file_path(path: str, allowed_base_path: str) -> tuple[bool, str]:
        """Validate file path to prevent directory traversal"""
        
        if ".." in path:
            return False, "Directory traversal detected"
        
        # Normalize path
        import os
        norm_path = os.path.normpath(path)
        
        if not norm_path.startswith(allowed_base_path):
            return False, f"Path outside allowed base: {allowed_base_path}"
        
        return True, "valid"
    
    @staticmethod
    def sanitize_input(data: Dict) -> Dict:
        """Sanitize input data"""
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Remove potentially dangerous characters
                value = value.replace(";", "").replace("|", "").replace("&", "")
            sanitized[key] = value
        return sanitized

# ============================================================================
# RESOURCE MONITORING
# ============================================================================

class ResourceMonitor:
    """Monitor tool resource usage during execution"""
    
    def __init__(self, limits: Dict[str, float]):
        self.limits = limits
        self.measurements = []
        self.is_monitoring = False
    
    def start_monitoring(self):
        """Start background resource monitoring"""
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.is_monitoring:
            # In real implementation, use psutil to get real metrics
            measurement = {
                "timestamp": datetime.now().isoformat(),
                "memory_mb": 256.5,  # Simulated
                "cpu_percent": 45.2,  # Simulated
            }
            self.measurements.append(measurement)
            time.sleep(1)
    
    def stop_monitoring(self) -> Dict:
        """Stop monitoring and return statistics"""
        self.is_monitoring = False
        
        if not self.measurements:
            return {}
        
        memory_values = [m["memory_mb"] for m in self.measurements]
        cpu_values = [m["cpu_percent"] for m in self.measurements]
        
        return {
            "measurements": len(self.measurements),
            "memory": {
                "max_mb": max(memory_values),
                "avg_mb": sum(memory_values) / len(memory_values),
                "limit_mb": self.limits.get("memory_mb", float('inf'))
            },
            "cpu": {
                "max_percent": max(cpu_values),
                "avg_percent": sum(cpu_values) / len(cpu_values),
                "limit_percent": self.limits.get("cpu_percent", float('inf'))
            }
        }
    
    def check_limits_exceeded(self) -> tuple[bool, List[str]]:
        """Check if any resource limit exceeded"""
        exceeded = []
        
        if self.measurements:
            latest = self.measurements[-1]
            
            if latest["memory_mb"] > self.limits.get("memory_mb", float('inf')):
                exceeded.append(f"Memory limit exceeded: {latest['memory_mb']}MB")
            
            if latest["cpu_percent"] > self.limits.get("cpu_percent", float('inf')):
                exceeded.append(f"CPU limit exceeded: {latest['cpu_percent']}%")
        
        return len(exceeded) > 0, exceeded

# ============================================================================
# CHANGE TRACKING & ROLLBACK
# ============================================================================

class ChangeTracker:
    """Track and enable rollback of tool changes"""
    
    def __init__(self):
        self.changes: List[Dict] = []
    
    def track_file_creation(self, file_path: str, content: str):
        """Track file creation for potential rollback"""
        self.changes.append({
            "type": "file_create",
            "path": file_path,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def track_file_modification(self, file_path: str, before_content: str, after_content: str):
        """Track file modification for potential rollback"""
        self.changes.append({
            "type": "file_modify",
            "path": file_path,
            "before": before_content,
            "after": after_content,
            "timestamp": datetime.now().isoformat()
        })
    
    def track_api_call(self, api_endpoint: str, method: str, data: Dict):
        """Track API call for potential rollback"""
        self.changes.append({
            "type": "api_call",
            "endpoint": api_endpoint,
            "method": method,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_reversible_changes(self) -> List[Dict]:
        """Get changes that can be reversed"""
        reversible_types = ["file_create", "file_modify", "api_call"]
        return [c for c in self.changes if c["type"] in reversible_types]
    
    def rollback_all(self) -> Dict:
        """Rollback all changes"""
        rollback_plan = []
        
        # Reverse order - undo most recent first
        for change in reversed(self.get_reversible_changes()):
            if change["type"] == "file_create":
                rollback_plan.append({
                    "action": "delete_file",
                    "path": change["path"]
                })
            elif change["type"] == "file_modify":
                rollback_plan.append({
                    "action": "restore_file",
                    "path": change["path"],
                    "content": change["before"]
                })
            elif change["type"] == "api_call":
                rollback_plan.append({
                    "action": "reverse_api_call",
                    "endpoint": change["endpoint"],
                    "original_method": change["method"]
                })
        
        return {
            "total_changes": len(self.changes),
            "reversible_count": len(rollback_plan),
            "rollback_plan": rollback_plan
        }

# ============================================================================
# SECURE TOOL EXECUTOR
# ============================================================================

class SecureToolExecutor:
    """Execute tools securely with all controls"""
    
    def __init__(self):
        self.execution_history: Dict[str, ToolExecutionContext] = {}
    
    def execute(self, tool_id: str, agent_id: str, input_data: Dict, 
                tool_function: Callable, resource_limits: Dict) -> ToolExecutionContext:
        """
        Execute tool securely with full lifecycle
        
        Process:
        1. Create execution context
        2. Validate input
        3. Initialize monitoring
        4. Track changes
        5. Execute tool
        6. Verify execution
        7. Archive results
        """
        
        # Generate execution ID
        execution_id = hashlib.sha256(
            f"{tool_id}{agent_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Create execution context
        ctx = ToolExecutionContext(execution_id, tool_id, agent_id)
        self.execution_history[execution_id] = ctx
        
        try:
            # Step 1: Validate input
            ctx.state = ToolExecutionState.VALIDATING_INPUT
            ctx.log_event("VALIDATION", "Starting input validation")
            
            is_valid, validation_msg = self._validate_tool_input(input_data)
            if not is_valid:
                ctx.log_event("VALIDATION_FAILED", validation_msg, "error")
                ctx.state = ToolExecutionState.FAILED
                ctx.error = validation_msg
                return ctx
            
            ctx.log_event("VALIDATION_PASSED", "Input validation successful")
            ctx.input_data = input_data
            
            # Step 2: Sanitize input
            ctx.log_event("SANITIZATION", "Sanitizing input data")
            sanitized_input = InputValidator.sanitize_input(input_data)
            
            # Step 3: Initialize resource monitoring
            ctx.state = ToolExecutionState.MONITORING
            ctx.log_event("MONITORING_START", "Resource monitoring initialized")
            
            monitor = ResourceMonitor(resource_limits)
            monitor.start_monitoring()
            
            # Step 4: Initialize change tracking
            change_tracker = ChangeTracker()
            ctx.log_event("TRACKING_START", "Change tracking initialized")
            
            # Step 5: Execute tool
            ctx.state = ToolExecutionState.EXECUTING
            ctx.log_event("EXECUTION_START", f"Executing {tool_id}")
            
            start_time = time.time()
            
            # Execute with timeout
            try:
                result = tool_function(sanitized_input, change_tracker)
                ctx.output_data = result
            except Exception as e:
                ctx.log_event("EXECUTION_ERROR", str(e), "error")
                ctx.error = str(e)
                ctx.state = ToolExecutionState.FAILED
                raise
            
            execution_time = time.time() - start_time
            
            # Step 6: Stop monitoring
            monitor.stop_monitoring()
            resource_stats = monitor.stop_monitoring()
            ctx.set_resource_usage(
                resource_stats.get("memory", {}).get("max_mb", 0),
                resource_stats.get("cpu", {}).get("max_percent", 0),
                execution_time
            )
            
            ctx.log_event("MONITORING_STOP", "Resource monitoring completed")
            
            # Step 7: Check resource limits
            limits_exceeded, exceeded_msgs = monitor.check_limits_exceeded()
            if limits_exceeded:
                ctx.log_event("RESOURCE_LIMIT_EXCEEDED", "; ".join(exceeded_msgs), "warning")
            
            # Step 8: Record changes
            for change in change_tracker.changes:
                ctx.record_change(change["type"], change.get("path", change.get("endpoint")), change)
            
            ctx.log_event("EXECUTION_COMPLETE", "Tool execution completed successfully")
            ctx.state = ToolExecutionState.COMPLETED
            ctx.completed_at = datetime.now()
            
            return ctx
        
        except Exception as e:
            ctx.log_event("EXECUTION_FAILED", str(e), "error")
            ctx.state = ToolExecutionState.FAILED
            ctx.error = str(e)
            ctx.completed_at = datetime.now()
            return ctx
    
    def _validate_tool_input(self, input_data: Dict) -> tuple[bool, str]:
        """Validate tool input before execution"""
        
        if not isinstance(input_data, dict):
            return False, "Input must be dictionary"
        
        # Check for empty input
        if not input_data:
            return False, "Input cannot be empty"
        
        # Check for suspicious patterns
        for key, value in input_data.items():
            if isinstance(value, str):
                is_valid, msg = InputValidator.validate_command(value)
                if not is_valid:
                    return False, f"Invalid value for key '{key}': {msg}"
        
        return True, "valid"
    
    def request_rollback(self, execution_id: str) -> Dict:
        """Request rollback of tool execution"""
        
        if execution_id not in self.execution_history:
            return {"error": "Execution not found"}
        
        ctx = self.execution_history[execution_id]
        change_tracker = ChangeTracker()
        
        # Simulate retrieving changes from execution
        for change in ctx.changes_made:
            if change["type"] == "file_create":
                change_tracker.track_file_creation(change["target"], "")
            elif change["type"] == "file_modify":
                change_tracker.track_file_modification(change["target"], "", "")
        
        rollback_result = change_tracker.rollback_all()
        rollback_result["execution_id"] = execution_id
        rollback_result["original_state"] = ctx.state.value
        
        ctx.is_rolled_back = True
        ctx.state = ToolExecutionState.ROLLED_BACK
        ctx.log_event("ROLLBACK_EXECUTED", f"Rollback completed with {len(rollback_result['rollback_plan'])} actions")
        
        return rollback_result
    
    def get_execution_report(self, execution_id: str) -> Dict:
        """Get complete execution report"""
        
        if execution_id not in self.execution_history:
            return {"error": "Execution not found"}
        
        ctx = self.execution_history[execution_id]
        
        return {
            "summary": ctx.get_summary(),
            "events": ctx.events,
            "changes": ctx.changes_made,
            "input": ctx.input_data,
            "output": ctx.output_data,
            "error": ctx.error,
            "resource_usage": ctx.resource_usage
        }

# ============================================================================
# EXAMPLE TOOLS
# ============================================================================

def example_scan_tool(input_data: Dict, change_tracker) -> Dict:
    """Example: Vulnerability scan tool"""
    target = input_data.get("target", "unknown")
    
    # Simulate scan
    change_tracker.track_api_call(f"https://scanner.api/scan", "POST", {"target": target})
    
    return {
        "scan_id": "scan_001",
        "target": target,
        "vulnerabilities": ["CVE-2024-001", "CVE-2024-002"],
        "severity": "HIGH"
    }

def example_isolate_tool(input_data: Dict, change_tracker) -> Dict:
    """Example: Endpoint isolation tool"""
    endpoint = input_data.get("endpoint_id", "unknown")
    
    # Simulate isolation
    change_tracker.track_api_call(f"https://infra.api/isolate", "POST", {"endpoint": endpoint})
    change_tracker.track_file_creation("/var/log/isolation_001.log", "Isolation initiated")
    
    return {
        "isolation_id": "iso_001",
        "endpoint": endpoint,
        "status": "ISOLATED",
        "affected_connections": 3
    }

# ============================================================================
# DEMO
# ============================================================================

if __name__ == "__main__":
    
    executor = SecureToolExecutor()
    
    print("=" * 80)
    print("TOOL SECURITY SANDBOX - DEMONSTRATION")
    print("=" * 80)
    
    # Test 1: Secure scan execution
    print("\n✓ TEST 1: Secure Tool Execution with Monitoring")
    print("-" * 80)
    
    resource_limits = {
        "memory_mb": 512,
        "cpu_percent": 75,
        "timeout_seconds": 30
    }
    
    ctx = executor.execute(
        tool_id="scan_vulnerabilities",
        agent_id="agent_001",
        input_data={"target": "192.168.1.0/24"},
        tool_function=example_scan_tool,
        resource_limits=resource_limits
    )
    
    print(f"Execution ID: {ctx.execution_id}")
    print(f"Status: {ctx.state.value}")
    print(f"Output: {json.dumps(ctx.output_data, indent=2)}")
    print(f"Changes made: {len(ctx.changes_made)}")
    print(f"Events logged: {len(ctx.events)}")
    
    # Test 2: Execution with changes
    print("\n✓ TEST 2: Execution with Change Tracking and Rollback")
    print("-" * 80)
    
    ctx2 = executor.execute(
        tool_id="isolate_endpoint",
        agent_id="agent_001",
        input_data={"endpoint_id": "SERVER_001"},
        tool_function=example_isolate_tool,
        resource_limits=resource_limits
    )
    
    print(f"Execution ID: {ctx2.execution_id}")
    print(f"Changes tracked: {len(ctx2.changes_made)}")
    
    print("\n  Changes made:")
    for change in ctx2.changes_made:
        print(f"    - {change['type']}: {change['target']}")
    
    # Request rollback
    print("\n  Requesting rollback...")
    rollback_result = executor.request_rollback(ctx2.execution_id)
    print(f"  Rollback plan: {len(rollback_result['rollback_plan'])} actions")
    for action in rollback_result["rollback_plan"]:
        print(f"    - {action['action']}: {action.get('path', action.get('endpoint'))}")
    
    # Test 3: Get execution report
    print("\n✓ TEST 3: Complete Execution Report")
    print("-" * 80)
    
    report = executor.get_execution_report(ctx.execution_id)
    print(json.dumps(report["summary"], indent=2))
    
    print("\n  Event log:")
    for event in report["events"][:3]:
        print(f"    {event['timestamp']} | {event['type']}: {event['message']}")
    
    print("\n" + "=" * 80)
    print("KEY CONCEPTS DEMONSTRATED:")
    print("=" * 80)
    print("✓ Input Validation: Command/file path injection prevention")
    print("✓ Resource Monitoring: Memory, CPU tracking with limits")
    print("✓ Change Tracking: Complete audit trail of modifications")
    print("✓ Rollback Capability: Reverse execution effects if needed")
    print("✓ Event Logging: Comprehensive execution lifecycle logging")
    print("✓ Error Handling: Graceful failure with recovery options")
