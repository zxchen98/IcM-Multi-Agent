"""
FastAPI WebSocket server using streaming callbacks and workflow assembly.
Thin transport-only layer.
"""

import asyncio
import json
import uuid
import traceback
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.graph import create_streaming_multi_agent_system, run_workflow_async
from streaming.callbacks import WebSocketStreamingCallbacks, set_session_callbacks, clear_session_callbacks, set_current_session_id


async def run_workflow_with_session(app_workflow, ticket_id: str, session_id: str):
    """Run workflow with session context maintained - ASYNC VERSION"""
    # Set session context in this async function
    set_current_session_id(session_id)
    # Run the workflow asynchronously
    return await run_workflow_async(app_workflow, ticket_id)


# Request/Response models
class ProcessTicketRequest(BaseModel):
    ticket_id: str


class ProcessTicketResponse(BaseModel):
    session_id: str
    status: str


app = FastAPI(title="IcM Multi-Agent System API - Streaming")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/process-ticket", response_model=ProcessTicketResponse)
async def process_ticket_endpoint(request: ProcessTicketRequest):
    session_id = str(uuid.uuid4())
    return ProcessTicketResponse(session_id=session_id, status="started")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[WEBSOCKET] Client connected")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("action") == "process_ticket":
                ticket_id = message.get("ticket_id")
                if ticket_id:
                    await process_ticket_with_real_streaming(ticket_id, websocket)
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "No ticket_id provided"
                    }))
            
            # Removed user_confirmation handling - auto-approve all actions

    except WebSocketDisconnect:
        print("[WEBSOCKET] Client disconnected")
    except Exception as e:
        print(f"[WEBSOCKET ERROR] {e}")
        print(f"[WEBSOCKET ERROR] Traceback: {traceback.format_exc()}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Server error: {str(e)}"
            }))
        except Exception:
            pass


async def process_ticket_with_real_streaming(ticket_id: str, websocket: WebSocket):
    session_id = str(uuid.uuid4())  # Generate unique session ID
    
    try:
        print(f"[PROCESSING] Starting streaming for: {ticket_id}, Session: {session_id}")
        callbacks = WebSocketStreamingCallbacks(websocket)
        # Store callbacks per session instead of globally
        set_session_callbacks(session_id, callbacks)
        # Set current session ID for agents to use
        set_current_session_id(session_id)
        
        await websocket.send_text(json.dumps({
            "type": "agent",
            "agent_name": "System",
            "content": f"🎯 Processing ticket: {ticket_id} (Session: {session_id})",
            "timestamp": datetime.now().isoformat()
        }))

        app_workflow = create_streaming_multi_agent_system(callbacks, session_id)

        # � OPTIMIZED: Direct async execution without thread pool
        # LangGraph now supports full async execution, eliminating event loop conflicts
        result = await run_workflow_with_session(app_workflow, ticket_id, session_id)

        print(f"[PROCESSING] Completed processing: {ticket_id}, Session: {session_id}")

        # Try to extract and send final result content
        try:
            final_messages = []
            if isinstance(result, dict):
                final_messages = result.get("messages", []) or []
            # Extract text content from assistant/ai messages
            final_texts = []
            for m in final_messages:
                if isinstance(m, dict):
                    role = m.get("role")
                    if role in ("assistant", "ai") and m.get("content"):
                        final_texts.append(m.get("content"))
                else:
                    content = getattr(m, "content", None)
                    role = getattr(m, "type", None) or getattr(m, "role", None)
                    if content and (role in ("assistant", "ai", None)):
                        final_texts.append(content)

            if final_texts:
                await websocket.send_text(json.dumps({
                    "type": "report",
                    "agent_name": "System",
                    "content": final_texts[-1],
                    "timestamp": datetime.now().isoformat()
                }))
        except Exception as _send_err:
            print(f"[WEBSOCKET WARN] Failed to send final result: {_send_err}")

    except Exception as e:
        print(f"[PROCESSING ERROR] {e}")
        print(f"[PROCESSING ERROR] Traceback: {traceback.format_exc()}")
        await websocket.send_text(json.dumps({
            "type": "agent",
            "agent_name": "System",
            "content": f"❌ Error processing ticket: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }))
    finally:
        # Clean up session callbacks when processing is done
        clear_session_callbacks(session_id)
        print(f"[CLEANUP] Cleared callbacks for session: {session_id}")


if __name__ == "__main__":
    print("🚀 Starting IcM Multi-Agent System - Streaming")
    print("📡 WebSocket endpoint: ws://localhost:8000/ws")
    print("🔗 REST API: http://localhost:8000/api")

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
