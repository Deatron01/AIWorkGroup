# foundry-project/backend/agents/supervisor.py
import logging
from core.event_bus import bus, Event
from core.schemas import FunctionContract, RecoveryPlan
from tools.model_manager import ModelManager

logger = logging.getLogger("SupervisorAgent")

class SupervisorAgent:
    """
    Powered by Gemma 2 (27B). Handles deep logical review and failure recovery.
    Intervenes when Workers are stuck in a failure loop.
    """
    def __init__(self):
        bus.subscribe("Critical_Pipeline_Failure", self.handle_pipeline_failure)
        bus.subscribe("System_Error_Encountered", self.handle_system_error)

    async def handle_pipeline_failure(self, event: Event) -> None:
        payload = event.payload
        comp_name = payload.get("component_name")
        func_name = payload.get("function_name")
        error_log = payload.get("error")
        
        # In a full system, we would retrieve the original contract from memory/cache here.
        # For demonstration, we assume it's passed in the payload or retrieved via DAG Tracker state.
        original_contract = payload.get("contract_dump", "Contract details missing.")

        logger.warning(f"[Supervisor] Analyzing critical failure for {comp_name}::{func_name}...")

        prompt = f"""
        A Worker agent failed to implement the following function after maximum retries.
        
        Original Contract:
        {original_contract}
        
        Error Log:
        {error_log}
        
        Analyze the failure. Was the specification impossible? Were the required imports missing? 
        Provide a recovery plan. If the architecture is fundamentally broken, flag it for escalation.
        """

        try:
            recovery: RecoveryPlan = await ModelManager.run_supervisor(
                prompt=prompt,
                schema=RecoveryPlan
            )

            logger.info(f"[Supervisor] Analysis complete. Requires Arch Change: {recovery.requires_architecture_change}")

            if recovery.requires_architecture_change:
                # Level 3 Escalation to the Boss
                await bus.publish(
                    topic="Architecture_Adjustment_Required",
                    payload={"component": comp_name, "analysis": recovery.analysis},
                    source="SupervisorAgent"
                )
            else:
                # Level 2 Retry: Re-issue the task with revised instructions
                logger.info(f"[Supervisor] Re-issuing task with revised instructions for {func_name}.")
                
                # We would normally update the specific contract fields here based on the recovery plan
                # and push it back to the DAG Tracker.
                await bus.publish(
                    topic="Task_Ready", # Forces the Worker to try again with the new context
                    payload={
                        "component_name": comp_name,
                        "contract": original_contract, 
                        "supervisor_notes": recovery.revised_purpose
                    },
                    source="SupervisorAgent"
                )

        except Exception as e:
            logger.error(f"[Supervisor] Failed to generate recovery plan: {str(e)}")

    async def handle_system_error(self, event: Event) -> None:
        # Handles raw unhandled exceptions from the Event Bus (e.g., JSON parse failures)
        logger.error(f"[Supervisor] System Error Detected: {event.payload}")

# Initialize singleton
supervisor_node = SupervisorAgent()