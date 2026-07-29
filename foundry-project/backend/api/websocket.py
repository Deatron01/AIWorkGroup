import asyncio
import json
from typing import List, Any, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from core.hitl_manager import hitl_manager

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print("[Gateway] Frontend connected to UI socket.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message_type: str, payload: Dict[str, Any]):
        """Serializes and pushes data to all connected UIs."""
        if not self.active_connections:
            return
            
        message = json.dumps({"type": message_type, "payload": payload})
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except RuntimeError:
                pass

manager = ConnectionManager()

@app.websocket("/ws/ui")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            
            if data.get("type") == "HUMAN_DECISION":
                payload = data.get("payload", {})
                task_id = payload.get("task_id")
                is_approved = payload.get("is_approved")
                feedback = payload.get("feedback", "")
                
                # Resolve the suspended future
                hitl_manager.resolve_approval(task_id, is_approved, feedback)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)