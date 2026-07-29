import asyncio
import uvicorn
from pydantic import BaseModel
from openai import AsyncOpenAI
from tools.sandbox_async import AsyncDockerSandbox
from core.event_bus import EventBus
from api.ui_bridge import UIBroadcaster
from api.websocket import manager, app
from core.dag_tracker import DAGTracker
from agents.boss import BossPlanner
from agents.worker import AsyncWorkerNode 
from agents.supervisor import Supervisor

from tools.model_manager import ModelManager

ollama_client = AsyncOpenAI(
    base_url="http://127.0.0.1:11434/v1",
    api_key="ollama"
)

BOSS_MODEL = "llama3.1:8b"
WORKER_MODEL = "qwen2.5-coder:7b"
model_manager = ModelManager()

# Initialize globals
sandbox = AsyncDockerSandbox("./workspace")
bus = EventBus()

# Define the expected JSON payload format
class ProjectRequest(BaseModel):
    goal: str

@app.post("/api/start-project")
async def start_project(request: ProjectRequest):
    print(f"\n Received new project goal: {request.goal}")
    
    # 1. Swapping VRAM: Ensure Worker is unloaded, Boss is preloaded
    await model_manager.switch_models(
        model_to_unload=WORKER_MODEL, 
        model_to_load=BOSS_MODEL
    )
    
    # 2. Run the async 3-Phase Boss Planner
    boss = BossPlanner(llm_client=ollama_client, model_name=BOSS_MODEL)
    plan_result = await boss.plan_project(request.goal)
    
    dag = plan_result["dag"]
    
    # Broadcast DAG to WebSockets UI
    await manager.broadcast("DAG_INIT", dag)
    
    # 3. Swapping VRAM: Drop Boss from VRAM and Load Worker for execution loop
    await model_manager.switch_models(
        model_to_unload=BOSS_MODEL, 
        model_to_load=WORKER_MODEL
    )
    
    # 4. Initialize tracker and start event bus processing
    tracker = DAGTracker(dag, bus)
    bus.subscribe("task.completed", tracker.handle_task_completed)
    
    await tracker.evaluate_graph()
    
    return {
        "status": "started", 
        "project_name": dag.get("project_name", "Mimir Project"), 
        "task_count": len(dag.get("tasks", []))
    }


async def main():
    # 1. Initialize core system
    print("Starting Docker sandbox environment...")
    sandbox.start()
    
    # 2. Attach the UI Bridge
    broadcaster = UIBroadcaster(bus, manager)
    
    # 3. Initialize the Supervisor using the sandbox
    # We pass None for the worker initially to avoid circular imports, 
    # then assign it right after.
    supervisor_node = Supervisor(sandbox=sandbox, worker_agent=None)
    
    # 4. Initialize Worker Pool, pass in the supervisor, and subscribe
    worker_pool = AsyncWorkerNode(bus)
    worker_pool.supervisor = supervisor_node
    supervisor_node.worker = worker_pool # Complete the two-way link
    
    bus.subscribe("task.ready", worker_pool.handle_ready_task)
    
    # 5. Start the Event Bus background task
    bus_task = asyncio.create_task(bus.run())
    
    # 6. Start the FastAPI server using Uvicorn programmatically
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    print("Backend Running on ws://127.0.0.1:8000/ws/ui")
    print("API ready at http://127.0.0.1:8000/api/start-project")
    
    try:
        await server.serve()
    finally:
        # Graceful shutdown
        print("\nShutting down sandbox and event bus...")
        sandbox.stop()
        bus_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())