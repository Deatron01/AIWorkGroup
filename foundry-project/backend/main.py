# foundry-project/backend/main.py
import asyncio
import uvicorn
from pydantic import BaseModel
from openai import AsyncOpenAI

# Core Framework
from tools.sandbox_async import AsyncDockerSandbox
from tools.model_manager import ModelManager, BOSS_MODEL, WORKER_MODEL, SUPERVISOR_MODEL
from core.event_bus import bus # Global singleton bus
from core.dag_tracker import dag_tracker

# UI Bridge & API
from api.ui_bridge import UIBroadcaster
from api.websocket import manager, app

# Agents (Importing them triggers their __init__ to subscribe to the Event Bus)
from agents.boss import boss_node
from agents.function_designer import function_designer_node
from agents.worker import worker_node
from agents.unit_tester import unit_tester_node
from agents.supervisor import supervisor_node
from agents.integrator import integrator_node

from startup import ensure_models_loaded

from core.database import init_db
from core.metrics_collector import metrics_collector

# Initialize Sandbox and Model Manager
sandbox = AsyncDockerSandbox("./workspace")
model_manager = ModelManager()

# Define the expected JSON payload format
class ProjectRequest(BaseModel):
    goal: str

# -------------------------------------------------------------------
# VRAM Management Hooks (Event-Driven)
# -------------------------------------------------------------------
async def load_supervisor_vram(event):
    """Triggered when Boss finishes. Swaps Llama 3.1 70B for Gemma 2 27B."""
    print("\n[VRAM Manager] Architecture Approved. Swapping Boss -> Supervisor...")
    await model_manager.switch_models(
        model_to_unload=BOSS_MODEL, 
        model_to_load=SUPERVISOR_MODEL
    )

async def load_worker_vram(event):
    """Triggered when Function Designer finishes. Swaps Gemma 2 27B for Qwen Code 14B."""
    print("\n[VRAM Manager] Contracts Ready. Swapping Supervisor -> Worker (The Forge)...")
    await model_manager.switch_models(
        model_to_unload=SUPERVISOR_MODEL, 
        model_to_load=WORKER_MODEL
    )

# Bind VRAM swaps to the cascade of events
bus.subscribe("Architecture_Approved", load_supervisor_vram)
bus.subscribe("Function_Contracts_Ready", load_worker_vram)


# -------------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------------
@app.post("/api/start-project")
async def start_project(request: ProjectRequest):
    print(f"\n[API] Received new project goal: {request.goal}")
    
    # 1. Swapping VRAM: Ensure Worker is unloaded, Boss is preloaded for initialization
    await model_manager.switch_models(
        model_to_unload=WORKER_MODEL, 
        model_to_load=BOSS_MODEL
    )
    
    # 2. Kick off the asynchronous pipeline by feeding the Boss
    # The Boss will emit "Architecture_Approved" when done, cascading through the system.
    asyncio.create_task(boss_node.initialize_project(request.goal))
    
    # Broadcast status to WebSockets UI immediately so the user isn't waiting on the HTTP request
    await manager.broadcast("SYSTEM_STATUS", {"status": "Boss Agent Analyzing Requirements"})
    
    return {
        "status": "started", 
        "project_name": "Project Mimir AI Factory", 
        "message": "Pipeline initialized. Event cascade started."
    }

# -------------------------------------------------------------------
# Main Bootstrapper
# -------------------------------------------------------------------
async def main():
    # 0. Run the pre-flight checks and download missing models
    await ensure_models_loaded()
    
    # 0. Initialize Database & Tables
    init_db()
    print("[System] Database initialized successfully.")
    
    # 1. Start background metrics collector loop
    asyncio.create_task(metrics_collector.start())
    
    # 1. Initialize core system (Docker Sandbox)
    print("\n[System] Starting Docker sandbox environment...")
    sandbox.start()
    
    # (Note: Agent singletons are already loaded in memory via imports and bound to the bus)
    
    # 2. Attach the UI Bridge
    broadcaster = UIBroadcaster(bus, manager)
    
    # 3. Start the FastAPI server using Uvicorn programmatically
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    print("\n=======================================================")
    print(" Project Mimir AI Factory Backend Running")
    print(" UI WebSockets: ws://127.0.0.1:8000/ws/ui")
    print(" API Endpoint:  http://127.0.0.1:8000/api/start-project")
    print("=======================================================\n")
    
    try:
        await server.serve()
    finally:
        # Graceful shutdown
        print("\n[System] Shutting down sandbox and releasing resources...")
        sandbox.stop()

if __name__ == "__main__":
    asyncio.run(main())