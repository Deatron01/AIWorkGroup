# foundry-project/backend/agents/boss.py
import logging
from core.event_bus import bus
from core.schemas import SystemArchitecture
from tools.model_manager import ModelManager

logger = logging.getLogger("BossAgent")

class BossAgent:
    """
    Powered by Llama 3.1 (70B). Ingests raw requirements and outputs 
    the rigid structural boundaries for the project.
    """
    async def initialize_project(self, raw_requirements: str) -> None:
        """
        The entry point for the entire AI Software Factory.
        """
        logger.info("[Boss] Analyzing raw user requirements...")

        prompt = f"""
        You are the Chief AI Systems Architect.
        Analyze the following requirements and define the system boundaries, major modules, and architecture.
        Do NOT write implementation details or code. 
        
        Requirements:
        {raw_requirements}
        """

        try:
            architecture: SystemArchitecture = await ModelManager.run_boss(
                prompt=prompt,
                schema=SystemArchitecture
            )

            logger.info(f"[Boss] Architecture approved for '{architecture.project_name}'. Modules: {architecture.components}")

            # Kick off the entire pipeline by publishing the Architecture_Approved event
            await bus.publish(
                topic="Architecture_Approved",
                payload={
                    "architecture": architecture.architecture_notes,
                    "components": architecture.components
                },
                source="BossAgent"
            )

        except Exception as e:
            logger.error(f"[Boss] Failed to generate architecture: {str(e)}")

# Initialize singleton
boss_node = BossAgent()