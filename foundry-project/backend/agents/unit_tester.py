# foundry-project/backend/agents/unit_tester.py
import logging
import asyncio
from typing import Any, Dict
from core.event_bus import bus, Event
from core.schemas import FunctionContract, ImplementationResult
from tools.sandbox_async import AsyncDockerSandbox

logger = logging.getLogger("UnitTesterAgent")

class UnitTesterAgent:
    """
    Deterministically validates code snippets emitted by the Worker.
    Performs syntax checking and isolated compilation/execution.
    """
    def __init__(self):
        bus.subscribe("Code_Generated", self.handle_code_validation)
        self.sandbox = AsyncDockerSandbox("./workspace")

    async def handle_code_validation(self, event: Event) -> None:
        payload: Dict[str, Any] = event.payload
        comp_name = payload.get("component_name")
        func_name = payload.get("function_name")
        contract_data = payload.get("contract")
        implementation_data = payload.get("implementation")

        contract = FunctionContract(**contract_data)
        implementation = ImplementationResult(**implementation_data)

        logger.info(f"[UnitTester] Validating syntax and constraints for {func_name}...")

        is_valid, error_msg = await self._run_sandbox_validation(contract, implementation)

        if is_valid:
            logger.info(f"[UnitTester] ✅ Validation passed for {func_name}.")
            await bus.publish(
                topic="Test_Passed",
                payload={
                    "component_name": comp_name,
                    "function_name": func_name,
                    "verified_code": implementation.source_code,
                    "imports": implementation.imports_required
                },
                source="UnitTesterAgent"
            )
        else:
            logger.warning(f"[UnitTester] ❌ Validation failed for {func_name}. Emitting Task_Failed.")
            await bus.publish(
                topic="Task_Failed",
                payload={
                    "component_name": comp_name,
                    "function_name": func_name,
                    "error": error_msg
                },
                source="UnitTesterAgent"
            )

    async def _run_sandbox_validation(self, contract: FunctionContract, implementation: ImplementationResult) -> tuple[bool, str]:
        """
        Executes the code in an isolated container to verify it compiles 
        and adheres to basic constraints (e.g., syntax errors, missing imports).
        """
        try:
            # Construct a testable snippet by prepending required imports
            imports_str = "\n".join(implementation.imports_required)
            testable_code = f"{imports_str}\n\n{implementation.source_code}"

            # We use Python's built-in compile() as a fast, deterministic syntax check for Python target code.
            # For C++/C#, this would invoke a lightweight compiler via the sandbox CLI.
            
            # Step 1: Fast Static Analysis (Syntax Check)
            compile(testable_code, f"{contract.function_name}_memory_file", 'exec')

            # Step 2: Sandbox Execution (Simulating compilation/import resolution)
            # This ensures the required imports actually exist and the code evaluates cleanly.
            sandbox_result = await self.sandbox.execute_code(
                code=testable_code,
                timeout=5.0 # Strict timeout to catch infinite loops (time complexity failures)
            )

            if sandbox_result.get("exit_code") != 0:
                return False, f"Sandbox execution failed: {sandbox_result.get('stderr')}"

            return True, ""

        except SyntaxError as e:
            return False, f"Syntax Error: {e.msg} at line {e.lineno}"
        except Exception as e:
            return False, f"Unexpected compilation error: {str(e)}"

# Initialize singleton
unit_tester_node = UnitTesterAgent()