from openai import AsyncOpenAI
from src.git_manager import GitTransactionManager

client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="local")
sandbox = AsyncDockerSandbox("./workspace")
bus = EventBus()

# Assume TaskGraph and TaskNode schemas remain from Phase 3

class DAGTracker:
    """Listens to task completions and emits 'task.ready' for unblocked nodes."""
    def __init__(self, plan: TaskGraph, bus: EventBus):
        self.plan = plan
        self.bus = bus
        self.completed_tasks = set()
        self.pending_tasks = {t.task_id: t for t in plan.tasks}

    async def handle_task_completed(self, payload: Dict[str, Any]):
        task_id = payload["task_id"]
        self.completed_tasks.add(task_id)
        if task_id in self.pending_tasks:
            del self.pending_tasks[task_id]
        
        print(f"\n[DAG Tracker] 🟢 Task {task_id} completed. Checking dependencies...")
        await self.evaluate_graph()

    async def evaluate_graph(self):
        if not self.pending_tasks:
            print("\n[DAG Tracker] 🎉 All tasks complete!")
            return

        for task_id, task in list(self.pending_tasks.items()):
            # If all dependencies are in the completed set, fire it off
            if all(dep in self.completed_tasks for dep in task.dependencies):
                if not getattr(task, "dispatched", False):
                    task.dispatched = True
                    print(f"[DAG Tracker] 🚀 Dispatching ready task: {task_id}")
                    await self.bus.publish("task.ready", {"task": task})
                    
git_manager = GitTransactionManager("./workspace")

class AsyncWorkerNode:
    def __init__(self, bus: EventBus):
        self.bus = bus

    async def handle_ready_task(self, payload: Dict[str, Any]):
        task = payload["task"]
        
        # 1. Start the transaction (creates branch task-<id>)
        # Using a thread pool to avoid blocking the async event loop with subprocess calls
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, git_manager.start_task_branch, task.task_id)
        
        success = await self._run_llm_retry_loop(task)

        if success:
            # 2. Merge on success
            commit_msg = f"Completed {task.task_id}: {task.description}"
            try:
                await loop.run_in_executor(None, git_manager.commit_and_merge, task.task_id, commit_msg)
                await self.bus.publish("task.completed", {"task_id": task.task_id})
            except RuntimeError as e:
                # E.g., Merge conflict
                print(f"[Worker] Error finalizing task: {e}")
                await self.bus.publish("task.failed", {"task_id": task.task_id, "reason": "merge_conflict"})
        else:
            # The retry loop exhausted its attempts
            await self.bus.publish("task.failed", {"task_id": task.task_id, "reason": "max_retries"})

    async def _run_llm_retry_loop(self, task, max_retries: int = 3) -> bool:
        attempt = 1
        current_prompt = task.description
        
        while attempt <= max_retries:
            # 1. Worker Generates Code
            # (Worker LLM chat execution goes here)
            
            # 2. Supervisor Verifies Code
            # (Supervisor LLM sandbox execution goes here)
            supervisor_verdict = "VERIFICATION_PASSED" # Simulated
            
            if "VERIFICATION_PASSED" in supervisor_verdict:
                # 3. HUMAN-IN-THE-LOOP GATE
                loop = asyncio.get_running_loop()
                diff = await loop.run_in_executor(None, git_manager.get_diff)
                
                # Broadcast the diff to the UI
                await self.bus.publish("task.awaiting_approval", {
                    "task_id": task.task_id,
                    "diff": diff
                })
                
                # Suspend execution until the human clicks Approve or Reject
                decision = await hitl_manager.wait_for_human(task.task_id)
                
                if decision["is_approved"]:
                    print(f"[Worker] ✅ Task {task.task_id} approved by human.")
                    return True
                else:
                    print(f"[Worker] ❌ Task {task.task_id} REJECTED by human.")
                    # Fall through to the rollback block below
                    rejection_reason = f"Human Review Failed: {decision['feedback']}"
                    current_prompt = f"Your previous code failed. {rejection_reason}\nFix the issues."
            else:
                current_prompt = f"Your previous code failed. Supervisor feedback: {supervisor_verdict}"

            # 4. Rollback on Failure (Supervisor or Human)
            print(f"[Worker] Rolling back changes for attempt {attempt}...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, git_manager.rollback_attempt)
            attempt += 1
                
        return False

# ---------------------------------------------------------
# 5. Bootstrapping the System
# ---------------------------------------------------------
async def main():
    sandbox.start()
    try:
        # 1. Start the event bus in the background
        bus_task = asyncio.create_task(bus.run())

        # 2. Setup a dummy graph (In reality, BossAgent generates this)
        mock_plan = TaskGraph(
            project_name="Parallel Demo",
            tasks=[
                TaskNode(task_id="setup", description="Init repo", role="programmer", dependencies=[]),
                TaskNode(task_id="db", description="Write DB schema", role="programmer", dependencies=["setup"]),
                TaskNode(task_id="api", description="Write API", role="programmer", dependencies=["setup"]),
                TaskNode(task_id="docs", description="Write Readme", role="architect", dependencies=["db", "api"])
            ]
        )

        # 3. Wire up the event subscribers
        tracker = DAGTracker(mock_plan, bus)
        worker_pool = AsyncWorkerNode(bus)

        bus.subscribe("task.completed", tracker.handle_task_completed)
        bus.subscribe("task.ready", worker_pool.handle_ready_task)

        # 4. Kickstart the graph
        await tracker.evaluate_graph()

        # Keep running until the tracker is empty
        while tracker.pending_tasks:
            await asyncio.sleep(1)
            
    finally:
        sandbox.stop()
        bus_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())