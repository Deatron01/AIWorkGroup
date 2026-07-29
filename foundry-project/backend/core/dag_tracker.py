from typing import Dict, Any, Set
from core.schemas import TaskGraph, TaskNode
from core.event_bus import EventBus
from typing import Dict, Union, Any

class DAGTracker:
    """Listens to task completions and emits 'task.ready' for unblocked nodes."""
    def __init__(self, plan: Union[dict, Any], bus):
        self.bus = bus
        self.completed_tasks = set()
        self.failed_tasks = set()
        self.dispatched_tasks = set()
        self.plan = plan
        
        # 1. Safely extract tasks array whether `plan` is a dict or Pydantic object
        if isinstance(plan, dict):
            raw_tasks = plan.get("tasks", [])
        else:
            raw_tasks = getattr(plan, "tasks", [])

        # 2. Build pending_tasks dictionary safely
        self.pending_tasks: Dict[str, Any] = {}
        for task in raw_tasks:
            if isinstance(task, dict):
                task_id = task.get("task_id")
                # If you have a TaskNode Pydantic model, instantiate it:
                # self.pending_tasks[task_id] = TaskNode(**task)
                self.pending_tasks[task_id] = task
            else:
                self.pending_tasks[task.task_id] = task

        print(f"[DAGTracker] Loaded {len(self.pending_tasks)} tasks into execution graph.")

    async def handle_task_completed(self, payload: Dict[str, Any]):
        task_id = payload["task_id"]
        self.completed_tasks.add(task_id)
        if task_id in self.pending_tasks:
            del self.pending_tasks[task_id]
        
        print(f"\n[DAG Tracker] Task {task_id} completed. Checking dependencies...")
        await self.evaluate_graph()

    async def evaluate_graph(self):
        if not self.pending_tasks:
            print("\n[DAG Tracker] All tasks complete!")
            # Safely handle self.plan whether it is a dictionary or an object
            project_name = self.plan.get("project_name", "Unknown") if isinstance(self.plan, dict) else getattr(self.plan, "project_name", "Unknown")
            await self.bus.publish("plan.completed", {"project_name": project_name})
            return

        for task_id, task in list(self.pending_tasks.items()):
            # Safely extract dependencies whether task is a dict or an object
            deps = task.get("dependencies", []) if isinstance(task, dict) else getattr(task, "dependencies", [])
            
            # If all dependencies are in the completed set, fire it off
            if all(dep in self.completed_tasks for dep in deps):
                # Check our local set instead of modifying the Pydantic object
                if task_id not in self.dispatched_tasks:
                    self.dispatched_tasks.add(task_id)
                    print(f"[DAG Tracker] Dispatching ready task: {task_id}")
                    await self.bus.publish("task.ready", {"task": task})