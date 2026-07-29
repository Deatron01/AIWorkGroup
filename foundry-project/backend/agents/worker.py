# foundry-project/backend/agents/worker.py
import logging
from core.event_bus import bus, Event
from core.schemas import FunctionContract, ImplementationResult
from tools.model_manager import ModelManager

logger = logging.getLogger("WorkerAgent")

class WorkerAgent:
    """
    The implementation specialist. 
    Listens for Task_Ready events, generates code via Qwen2.5-Coder, 
    and emits the raw code for the Unit Tester to evaluate.
    """
    def __init__(self):
        # Bind this microservice to the event bus
        bus.subscribe("Task_Ready", self.handle_task)
        # Track retries to prevent infinite loops
        self.task_retries = {}
        self.MAX_RETRIES = 3

    async def handle_task(self, event: Event) -> None:
        payload = event.payload
        comp_name = payload.get("component_name")
        contract: FunctionContract = payload.get("contract")
        
        task_id = f"{comp_name}::{contract.function_name}"
        self.task_retries.setdefault(task_id, 0)

        logger.info(f"[Worker] Picked up task: {contract.function_name} (Attempt {self.task_retries[task_id] + 1})")

        # 1. Formulate the strict context prompt
        prompt = self._build_prompt(contract)

        try:
            # 2. Invoke Qwen2.5-Coder via ModelManager (forces JSON schema adherence)
            result: ImplementationResult = await ModelManager.run_worker(
                prompt=prompt,
                schema=ImplementationResult
            )

            # 3. Pass the generated code to the Unit Tester node
            logger.info(f"[Worker] Generation successful for {contract.function_name}. Emitting for testing.")
            await bus.publish(
                topic="Code_Generated",
                payload={
                    "component_name": comp_name,
                    "function_name": contract.function_name,
                    "contract": contract.model_dump(),
                    "implementation": result.model_dump()
                },
                source="WorkerAgent"
            )
            
            # Clear retries on success
            if task_id in self.task_retries:
                del self.task_retries[task_id]

        except Exception as e:
            logger.warning(f"[Worker] Qwen generation failed for {contract.function_name}: {str(e)}")
            self.task_retries[task_id] += 1
            
            if self.task_retries[task_id] >= self.MAX_RETRIES:
                logger.error(f"[Worker] Max retries reached for {contract.function_name}. Escalating failure.")
                await bus.publish(
                    topic="Task_Failed",
                    payload={
                        "component_name": comp_name,
                        "function_name": contract.function_name,
                        "error": f"Failed after {self.MAX_RETRIES} attempts. Last error: {str(e)}"
                    },
                    source="WorkerAgent"
                )
            else:
                # Re-queue the task for another attempt
                await asyncio.sleep(2) # Brief backoff
                await bus.publish(topic="Task_Ready", payload=payload, source="WorkerAgent")

    def _build_prompt(self, contract: FunctionContract) -> str:
        """
        Creates a hyper-focused prompt. The Worker sees ONLY this contract.
        """
        return f"""
You are required to implement the following function exactly as specified.
Do not write a main function, do not write test cases, and do not invent new interfaces.

Function Name: {contract.function_name}
Purpose: {contract.purpose}
Parameters: {contract.parameters}
Return Type: {contract.return_type}
Exceptions Allowed: {contract.exceptions_raised}
Side Effects: {contract.side_effects}
Thread Safety: {contract.thread_safety}
Time Complexity Target: {contract.time_complexity_expectation}

Write the optimal, production-grade code. Return the raw source code and list any standard library imports required.
"""

# Initialize singleton to bind it to the runtime memory
worker_node = WorkerAgent()