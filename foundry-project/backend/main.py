import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.event_bus import EventBus
from core.hitl_manager import HitLManager 
from api.ui_bridge import UIBroadcaster
from tools.sandbox_async import AsyncDockerSandbox

app = FastAPI()

# 1. Enable CORS so your Vite/Tauri frontend can talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Define the payload expected when the button is clicked
class TaskRequest(BaseModel):
    task: str

# 3. Add the POST route that the button is trying to call
@app.post("/start-task")
async def start_task(req: TaskRequest):
    print(f"[Backend] Received signal to start task: {req.task}")
    
    try:
        # 1. Instantiate the Boss Agent
        from agents.boss import BossAgent
        boss = BossAgent()
        
        # 2. Generate the TaskGraph (DAG) using the user's input goal
        # Note: boss.plan() is synchronous because it uses OpenAI's client.chat.completions.create
        task_graph = boss.plan(req.task)
        
        # 3. Publish the generated plan to your Event Bus 
        # (This triggers 'plan.created' which your UIBroadcaster maps to 'DAG_INIT')
        # Adjust the method/topic name depending on your event_bus implementation (e.g., bus.publish or bus.emit)
        await bus.publish("plan.created", task_graph.model_dump())
        
        return {
            "status": "success", 
            "message": f"Task '{req.task}' planned successfully.",
            "project_name": task_graph.project_name,
            "task_count": len(task_graph.tasks)
        }
    except Exception as e:
        print(f"[Error] Failed to execute boss plan: {str(e)}")
        return {"status": "error", "message": str(e)}

async def main():
    sandbox = AsyncDockerSandbox(workspace_path="./workspace") 
    sandbox.start()
    
    bus = EventBus()
    manager = HitLManager() 
    
    broadcaster = UIBroadcaster(bus, manager)
    
    bus_task = asyncio.create_task(bus.run())
    
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    print("Foundry Backend Running on ws://127.0.0.1:8000/ws/ui")
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())