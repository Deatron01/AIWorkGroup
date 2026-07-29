import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict

app = FastAPI(title="Foundry Control Center API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    """Manages active WebSocket connections for live telemetry."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# --- REST ENDPOINTS (Job Management & History) ---

@app.post("/api/jobs/start")
async def start_job(config: dict):
    # Logic to initialize a new Job ID and kick off the Boss Planner
    return {"job_id": "job_12345", "status": "Pending"}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    # Fetch job status, progress, and assigned workers from DB
    return {"job_id": job_id, "status": "Architecture", "progress": 15}

@app.get("/api/artifacts/{job_id}/files")
async def get_job_files(job_id: str):
    # Return file tree for the Project Explorer
    return {"files": ["main.py", "models/schemas.py", "README.md"]}

# --- WEBSOCKET ENDPOINT (Live Observability) ---

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client commands (Pause, Stop)
            data = await websocket.receive_text()
            print(f"Client command received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)