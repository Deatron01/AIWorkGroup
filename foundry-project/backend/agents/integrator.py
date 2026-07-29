# foundry-project/backend/agents/integrator.py
import logging
from typing import Dict, List, Set
from core.event_bus import bus, Event
from tools.file_ops import read_file, write_file, list_workspace, archive_workspace

logger = logging.getLogger("IntegratorAgent")

class IntegratorAgent:
    """
    Assembles validated functions into final production files.
    Ensures that no broken code ever reaches the main repository.
    """
    def __init__(self):
        # Cache for validated code snippets: {component_name: [code_strings]}
        self.verified_components: Dict[str, List[str]] = {}
        self.component_imports: Dict[str, Set[str]] = {}
        
        bus.subscribe("Test_Passed", self.handle_verified_function)
        bus.subscribe("Component_Ready", self.handle_component_assembly)

    async def handle_verified_function(self, event: Event) -> None:
        """
        Stores the verified code snippet and its required imports in memory.
        """
        payload = event.payload
        comp_name = payload.get("component_name")
        func_name = payload.get("function_name")
        verified_code = payload.get("verified_code")
        imports = payload.get("imports", [])

        if comp_name not in self.verified_components:
            self.verified_components[comp_name] = []
            self.component_imports[comp_name] = set()

        self.verified_components[comp_name].append(verified_code)
        
        for imp in imports:
            self.component_imports[comp_name].add(imp)
            
        logger.info(f"[Integrator] Cached verified function: {func_name} for component: {comp_name}")

    async def handle_component_assembly(self, event: Event) -> None:
        """
        Triggered when the DAG Tracker confirms every function in a component has passed testing.
        Assembles the file and writes it to the file system.
        """
        payload = event.payload
        comp_name = payload.get("component_name")
        
        if comp_name not in self.verified_components:
            logger.error(f"[Integrator] Received Component_Ready for {comp_name}, but no code is cached.")
            return

        logger.info(f"[Integrator] Assembling final file for {comp_name}...")

        # 1. Gather all unique imports
        all_imports = sorted(list(self.component_imports[comp_name]))
        imports_block = "\n".join(all_imports)

        # 2. Gather all verified function snippets
        functions_block = "\n\n".join(self.verified_components[comp_name])

        # 3. Assemble the final module
        final_file_content = f"{imports_block}\n\n{functions_block}\n"

        # 4. Write to disk (e.g., inside an output or src directory)
        file_path = f"generated_src/{comp_name.lower().replace(' ', '_')}.py"
        
        try:
            # Assuming file_ops has an async write method
            await write_file(file_path, final_file_content)
            logger.info(f"[Integrator] ✅ Successfully assembled and wrote {file_path}")
            
            # Clean up memory
            del self.verified_components[comp_name]
            del self.component_imports[comp_name]
            
            # Notify the system that a major module is integrated
            await bus.publish("Integration_Successful", {"file": file_path, "component": comp_name}, "IntegratorAgent")
            
        except Exception as e:
            logger.error(f"[Integrator] Failed to write {file_path}: {str(e)}")
            await bus.publish("System_Error_Encountered", {"error": str(e)}, "IntegratorAgent")

# Initialize singleton
integrator_node = IntegratorAgent()