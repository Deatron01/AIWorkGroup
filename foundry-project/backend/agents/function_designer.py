# foundry-project/backend/agents/function_designer.py
import logging
from core.event_bus import bus, Event
from core.schemas import ComponentScope
from tools.model_manager import ModelManager

logger = logging.getLogger("FunctionDesignerAgent")

class FunctionDesignerAgent:
    """
    The Decomposition layer. Translates high-level system components 
    into strict, atomic Function Contracts.
    """
    def __init__(self):
        bus.subscribe("Architecture_Approved", self.handle_architecture)

    async def handle_architecture(self, event: Event) -> None:
        """
        Ingests the global architecture and breaks it down component by component.
        """
        payload = event.payload
        architecture_definition = payload.get("architecture")
        components_to_design = payload.get("components", [])

        logger.info(f"[FunctionDesigner] Received approved architecture. Designing {len(components_to_design)} components...")

        for comp_name in components_to_design:
            prompt = f"""
            System Architecture:
            {architecture_definition}
            
            You are tasked with designing the strict API surface and internal function breakdown 
            for the component: '{comp_name}'.
            
            Decompose this component into atomic, single-responsibility functions. 
            Define their inputs, outputs, side effects, and dependencies on each other.
            Ensure you include 'depends_on' arrays to define the execution order (DAG).
            """

            try:
                # We can use the Supervisor model (Gemma 2) here, as it is highly logical
                # and 27B is sufficient for API design without wasting 70B compute.
                component_scope: ComponentScope = await ModelManager.run_supervisor(
                    prompt=prompt,
                    schema=ComponentScope
                )

                # Ensure the component name matches the requested design
                component_scope.component_name = comp_name

                logger.info(f"[FunctionDesigner] Successfully designed {len(component_scope.functions)} functions for {comp_name}.")
                
                # Emit to the DAG Tracker to begin the execution phase
                await bus.publish(
                    topic="Function_Contracts_Ready",
                    payload=component_scope,
                    source="FunctionDesignerAgent"
                )

            except Exception as e:
                logger.error(f"[FunctionDesigner] Failed to design component {comp_name}: {str(e)}")
                # Emit error for the Supervisor to analyze
                await bus.publish(
                    topic="System_Error_Encountered",
                    payload={"failed_node": "FunctionDesigner", "component": comp_name, "error": str(e)},
                    source="FunctionDesignerAgent"
                )

# Initialize singleton
function_designer_node = FunctionDesignerAgent()