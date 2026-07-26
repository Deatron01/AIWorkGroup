import asyncio
from typing import Dict

class HitLManager:
    def __init__(self):
        # Maps task_id -> asyncio.Future
        self.pending_approvals: Dict[str, asyncio.Future] = {}

    async def wait_for_human(self, task_id: str) -> dict:
        """Suspends the worker coroutine until a human responds."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_approvals[task_id] = future
        
        print(f"[HitL] 🛑 Task {task_id} paused. Awaiting human approval...")
        # This await yields control back to the event loop so other workers can run
        return await future 

    def resolve_approval(self, task_id: str, is_approved: bool, feedback: str = ""):
        """Called by the WebSocket gateway when the UI sends a response."""
        if task_id in self.pending_approvals:
            future = self.pending_approvals[task_id]
            if not future.done():
                future.set_result({
                    "is_approved": is_approved,
                    "feedback": feedback
                })
            del self.pending_approvals[task_id]
        else:
            print(f"[HitL] Warning: Attempted to resolve unknown task {task_id}")

hitl_manager = HitLManager()