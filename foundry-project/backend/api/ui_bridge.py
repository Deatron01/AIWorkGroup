from typing import Dict, Any
from core.event_bus import EventBus
# Assuming ConnectionManager is in your websocket.py file:
from api.websocket import ConnectionManager
class UIBroadcaster:
    def __init__(self, bus: EventBus, manager: ConnectionManager):
        self.bus = bus
        self.manager = manager
        
        # Subscribe to internal topics and map them to UI events
        self.bus.subscribe("task.ready", self.on_task_update)
        self.bus.subscribe("task.completed", self.on_task_update)
        self.bus.subscribe("task.failed", self.on_task_update)
        self.bus.subscribe("agent.log", self.on_agent_log)
        self.bus.subscribe("plan.created", self.on_plan_created)

    async def on_plan_created(self, payload: Dict[str, Any]):
        # Broadcast the initial DAG structure
        await self.manager.broadcast("DAG_INIT", payload)

    async def on_task_update(self, payload: Dict[str, Any]):
        # E.g., changing a node color from Blue (Ready) to Green (Completed)
        await self.manager.broadcast("TASK_STATUS_CHANGE", payload)

    async def on_agent_log(self, payload: Dict[str, Any]):
        # Streaming terminal output: { "task_id": "...", "agent": "Worker", "log": "..." }
        await self.manager.broadcast("AGENT_LOG", payload)