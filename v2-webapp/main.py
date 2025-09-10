"""Backward-compatible entry that forwards to streaming.transport.websocket_server app."""

from streaming.transport.websocket_server import app  # re-export for uvicorn discovery

if __name__ == "__main__":
    print("🚀 Starting IcM Multi-Agent System - Streaming")
    print("📡 WebSocket endpoint: ws://localhost:8000/ws")
    print("🔗 REST API: http://localhost:8000/api")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)