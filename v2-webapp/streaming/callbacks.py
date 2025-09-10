"""
Streaming Callbacks Interface and implementations.
Moved from top-level streaming_callbacks.py to streaming/callbacks.py
"""

# Import for threading support
import threading
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
import json
import uuid


class AgentStreamingCallbacks(ABC):
    """Abstract base class for agent streaming callbacks"""

    @abstractmethod
    async def on_agent_start(self, agent_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Called when an agent starts processing"""
        pass

    @abstractmethod
    async def on_agent_message(self, agent_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Called when an agent sends a message"""
        pass

    @abstractmethod
    async def on_tool_start(self, agent_name: str, tool_name: str, input_args: Dict[str, Any]):
        """Called when a tool starts executing"""
        pass

    @abstractmethod
    async def on_tool_end(self, agent_name: str, tool_name: str, result: Any):
        """Called when a tool finishes executing"""
        pass

    @abstractmethod
    async def on_handoff(self, from_agent: str, to_agent: str, reason: str):
        """Called when control is handed off between agents"""
        pass

    @abstractmethod
    async def on_final_result(self, agent_name: str, result: str):
        """Called when the final result is ready"""
        pass

    @abstractmethod
    async def on_agent_end(self, agent_name: str, message: str):
        """Called when an agent finishes processing"""
        pass

    # Removed confirmation methods - auto-approve all actions


class WebSocketStreamingCallbacks(AgentStreamingCallbacks):
    """WebSocket implementation of streaming callbacks - simplified without confirmations"""

    def __init__(self, websocket):
        self.websocket = websocket

    async def on_agent_start(self, agent_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Send agent start message to WebSocket"""
        await self._send_message({
            "type": "agent",
            "agent_name": agent_name,
            "content": f"🎯 {message}",
            "timestamp": datetime.now().isoformat(),
            "context": context or {}
        })

    async def on_agent_message(self, agent_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Send agent message to WebSocket"""
        await self._send_message({
            "type": "agent",
            "agent_name": agent_name,
            "content": message,
            "timestamp": datetime.now().isoformat(),
            "context": context or {}
        })

    async def on_tool_start(self, agent_name: str, tool_name: str, input_args: Dict[str, Any]):
        """Send tool start message to WebSocket"""
        # Format input args for display
        args_display = self._format_tool_args(input_args)

        await self._send_message({
            "type": "tool",
            "agent_name": agent_name,
            "tool_name": tool_name,
            # Some UIs render only 'content'; duplicate for reliability
            "command": args_display,
            "content": args_display,
            "result": "Executing...",
            "status": "running",
            "timestamp": datetime.now().isoformat()
        })

    async def on_tool_end(self, agent_name: str, tool_name: str, result: Any):
        """Send tool result message to WebSocket as separate message"""
        # Format result for display (robust to formatter errors)
        try:
            result_display = self._format_tool_result(result)
        except Exception as _fmt_err:
            print(f"[STREAMING WARN] Failed to format tool result: {_fmt_err}")
            result_display = str(result)

        await self._send_message({
            "type": "tool_result",
            "agent_name": agent_name,
            "tool_name": tool_name,
            "result": result_display,
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        })

    async def on_handoff(self, from_agent: str, to_agent: str, reason: str):
        """Send handoff message to WebSocket"""
        await self._send_message({
            "type": "handoff",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })

    async def on_final_result(self, agent_name: str, result: str):
        """Send final result to WebSocket"""
        await self._send_message({
            "type": "report",
            "agent_name": agent_name,
            "content": result,
            "timestamp": datetime.now().isoformat()
        })

    async def on_agent_end(self, agent_name: str, message: str):
        """Send agent end message to WebSocket"""
        await self._send_message({
            "type": "agent",
            "agent_name": agent_name,
            "content": message,
            "status": "ended",
            "timestamp": datetime.now().isoformat()
        })

    # Removed all confirmation methods - auto-approve all actions

    async def _send_message(self, message: Dict[str, Any]):
        """Internal method to send messages to WebSocket"""
        try:
            await self.websocket.send_text(json.dumps(message))
            print(f"[STREAMING] Sent: {message['type']} - {message.get('agent_name', message.get('tool_name', 'System'))}")
        except Exception as e:
            print(f"[STREAMING ERROR] Failed to send message: {e}")

    def _format_tool_args(self, args: Dict[str, Any]) -> str:
        """Format tool arguments for display"""
        if not args:
            return "No arguments provided"

        # For Kusto queries, return the actual query
        if "query" in args:
            return str(args["query"]).strip()

        # For Azure CLI commands, return the actual command
        if "command" in args:
            return str(args["command"]).strip()

        # For incident ID extraction
        if "incident_id" in args:
            return f"Incident ID: {args['incident_id']}"
        
        # For operations with descriptive info
        if "operation" in args:
            operation = args["operation"]
            extra_info = []
            if "container" in args:
                extra_info.append(f"Container: {args['container']}")
            if "test_name" in args:
                extra_info.append(f"Test: {args['test_name']}")
            if "title" in args:
                extra_info.append(f"Title: {args['title'][:100]}...")
            
            if extra_info:
                return f"Operation: {operation}\n" + "\n".join(extra_info)
            else:
                return f"Operation: {operation}"

        # For other tools, show a formatted version of the arguments
        try:
            import json
            # Filter out very long values to keep display clean
            display_args = {}
            for key, value in args.items():
                if isinstance(value, str) and len(value) > 200:
                    display_args[key] = value[:200] + "..."
                else:
                    display_args[key] = value
            
            return json.dumps(display_args, indent=2, ensure_ascii=False)
        except Exception:
            return str(args)

    def _format_tool_result(self, result: Any) -> str:
        """Format tool result for display"""
        if result is None:
            return "No result"

        if isinstance(result, dict):
            # For structured data like incident details, show the full JSON
            import json as _json

            # Try to import numpy; fall back gracefully if unavailable
            np = None
            try:
                import numpy as _np  # type: ignore
                np = _np
            except Exception:
                np = None

            try:
                # Clean and format the dictionary
                cleaned_result = {}
                for key, value in result.items():
                    cleaned_value = value
                    # Convert numpy types to Python native types if numpy is available
                    if np is not None:
                        try:
                            if isinstance(value, (np.integer,)):
                                cleaned_value = int(value)
                            elif isinstance(value, (np.floating,)):
                                cleaned_value = float(value)
                        except Exception:
                            cleaned_value = value

                    if hasattr(cleaned_value, 'isoformat'):
                        cleaned_value = cleaned_value.isoformat() if cleaned_value is not None else None
                    elif str(type(cleaned_value)).startswith('<class \'pandas'):
                        cleaned_value = str(cleaned_value) if cleaned_value is not None else None
                    elif isinstance(cleaned_value, str):
                        # Clean text fields
                        cleaned_value = cleaned_value.replace('\\n', ' ').replace('\n', ' ').replace('\\t', ' ').replace('\t', ' ')
                        # Truncate long text fields
                        if key.lower() in ['summary', 'mergedtext', 'description'] and len(cleaned_value) > 300:
                            cleaned_value = "..." + cleaned_value[-500:]
                        elif len(cleaned_value) > 500:
                            cleaned_value = cleaned_value[:500] + "..."

                    cleaned_result[key] = cleaned_value

                return _json.dumps(cleaned_result, indent=2, ensure_ascii=False)
            except Exception as e:
                return f"Error formatting result: {str(e)}"
        elif isinstance(result, list):
            if len(result) == 0:
                return "No results found"
            else:
                # For lists, show the full content if reasonable size
                import json as _json
                try:
                    if len(result) <= 10:  # Show full content for small lists
                        return _json.dumps(result, indent=2, ensure_ascii=False)
                    else:
                        return f"Found {len(result)} results:\n" + _json.dumps(result[:5], indent=2, ensure_ascii=False) + f"\n... and {len(result) - 5} more"
                except Exception:
                    return f"Found {len(result)} results"
        else:
            result_str = str(result)
            if len(result_str) > 1000:  # Increased limit for better visibility
                result_str = result_str[:1000] + "..."
            return result_str


class ConsoleStreamingCallbacks(AgentStreamingCallbacks):
    """Console implementation for debugging"""

    async def on_agent_start(self, agent_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        print(f"[AGENT START] {agent_name}: {message}")

    async def on_agent_message(self, agent_name: str, message: str, context: Optional[Dict[str, Any]] = None):
        print(f"[AGENT MSG] {agent_name}: {message}")

    async def on_tool_start(self, agent_name: str, tool_name: str, input_args: Dict[str, Any]):
        print(f"[TOOL START] {agent_name} -> {tool_name}: {input_args}")

    async def on_tool_end(self, agent_name: str, tool_name: str, result: Any):
        print(f"[TOOL END] {agent_name} -> {tool_name}: {result}")

    async def on_handoff(self, from_agent: str, to_agent: str, reason: str):
        print(f"[HANDOFF] {from_agent} -> {to_agent}: {reason}")

    async def on_final_result(self, agent_name: str, result: str):
        print(f"[FINAL] {agent_name}: {result}")

    async def on_agent_end(self, agent_name: str, message: str):
        print(f"[AGENT END] {agent_name}: {message}")

    # Removed confirmation methods - auto-approve all actions




# Session-based callback instances for concurrent support
_session_callbacks: Dict[str, AgentStreamingCallbacks] = {}
_callbacks_lock = threading.Lock()
_current_session_id: Optional[str] = None  # Track current session for agents


def set_session_callbacks(session_id: str, callbacks: AgentStreamingCallbacks):
    """Set callbacks for a specific session"""
    with _callbacks_lock:
        _session_callbacks[session_id] = callbacks


def get_session_callbacks(session_id: str) -> Optional[AgentStreamingCallbacks]:
    """Get callbacks for a specific session"""
    with _callbacks_lock:
        return _session_callbacks.get(session_id)


def clear_session_callbacks(session_id: str):
    """Clear callbacks for a specific session"""
    with _callbacks_lock:
        _session_callbacks.pop(session_id, None)


def set_current_session_id(session_id: str):
    """Set the current session ID for agents to use"""
    global _current_session_id
    _current_session_id = session_id


def get_current_callbacks() -> Optional[AgentStreamingCallbacks]:
    """Get callbacks for the current session"""
    global _current_session_id
    if _current_session_id:
        callbacks = get_session_callbacks(_current_session_id)
        if callbacks:
            return callbacks
    return None
