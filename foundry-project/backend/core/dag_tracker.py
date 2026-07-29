# foundry-project/backend/core/dag_tracker.py
import asyncio
import logging
from typing import Dict, List, Set
from .event_bus import bus, Event
from .schemas import ComponentScope, FunctionContract

logger = logging.getLogger("DAGTracker")

class DAGTracker:
    """
    Manages the dependency graph for function generation.
    Ensures maximum parallelization by unlocking tasks only when 
    their prerequisites are successfully completed and tested.
    """
    def __init__(self):
        # Maps component_name to a dictionary of function dependencies
        self.graphs: Dict[str, Dict[str, List[str]]] = {}
        self.pending_tasks: Dict[str, Dict[str, FunctionContract]] = {}
        
        # Track state of each function
        self.completed_nodes: Dict[str, Set[str]] = {}
        self.in_progress_nodes: Dict[str, Set[str]] = {}

        # Subscribe to relevant events
        bus.subscribe("Function_Contracts_Ready", self.handle_new_contracts)
        bus.subscribe("Test_Passed", self.handle_task_completed)
        bus.subscribe("Task_Failed", self.handle_task_failed)

    async def handle_new_contracts(self, event: Event) -> None:
        """
        Triggered when the Function Designer finishes specifying a component.
        Builds the DAG and immediately dispatches leaf nodes (0 dependencies).
        """
        payload: ComponentScope = event.payload
        comp_name = payload.component_name
        
        self.graphs[comp_name] = {}
        self.pending_tasks[comp_name] = {}
        self.completed_nodes[comp_name] = set()
        self.in_progress_nodes[comp_name] = set()

        for func in payload.functions:
            # Note: Assumes `depends_on` was added to FunctionContract schema
            dependencies = getattr(func, "depends_on", [])
            self.graphs[comp_name][func.function_name] = dependencies
            self.pending_tasks[comp_name][func.function_name] = func

        logger.info(f"[{comp_name}] DAG built with {len(payload.functions)} nodes.")
        await self._dispatch_ready_tasks(comp_name)

    async def _dispatch_ready_tasks(self, comp_name: str) -> None:
        """
        Scans the graph for functions whose dependencies are completely resolved,
        and pushes them to the event bus for Workers to pick up.
        """
        graph = self.graphs.get(comp_name, {})
        completed = self.completed_nodes.get(comp_name, set())
        in_progress = self.in_progress_nodes.get(comp_name, set())

        tasks_dispatched = 0

        for func_name, dependencies in graph.items():
            # Skip if already done or currently being worked on
            if func_name in completed or func_name in in_progress:
                continue
            
            # Check if all dependencies are in the 'completed' set
            if all(dep in completed for dep in dependencies):
                contract = self.pending_tasks[comp_name][func_name]
                
                # Mark as in progress and dispatch to workers
                in_progress.add(func_name)
                tasks_dispatched += 1
                
                logger.info(f"[{comp_name}] Dispatching task: {func_name}")
                await bus.publish(
                    topic="Task_Ready",
                    payload={"component_name": comp_name, "contract": contract},
                    source="DAGTracker"
                )

        if tasks_dispatched == 0 and len(completed) < len(graph):
            # If nothing was dispatched and we aren't done, we might have a circular dependency or a stall.
            logger.warning(f"[{comp_name}] Pipeline stalled. Possible circular dependency or failed worker.")

    async def handle_task_completed(self, event: Event) -> None:
        """
        Triggered when the Unit Tester (or Supervisor) confirms the code is production-ready.
        """
        payload = event.payload
        comp_name = payload.get("component_name")
        func_name = payload.get("function_name")

        if comp_name in self.graphs:
            if func_name in self.in_progress_nodes[comp_name]:
                self.in_progress_nodes[comp_name].remove(func_name)
            
            self.completed_nodes[comp_name].add(func_name)
            logger.info(f"[{comp_name}] Node resolved: {func_name}. Unlocking dependents...")
            
            # Check if this unlocks new tasks
            await self._dispatch_ready_tasks(comp_name)
            
            # Check if the entire component is finished
            if len(self.completed_nodes[comp_name]) == len(self.graphs[comp_name]):
                logger.info(f"[{comp_name}] All functions completed. Emitting Component_Ready.")
                await bus.publish("Component_Ready", {"component_name": comp_name}, "DAGTracker")

    async def handle_task_failed(self, event: Event) -> None:
        """
        Triggered if a Worker exhausted its retry attempts.
        Removes the task from 'in_progress' so the pipeline doesn't permanently lock.
        """
        payload = event.payload
        comp_name = payload.get("component_name")
        func_name = payload.get("function_name")
        
        if comp_name in self.graphs and func_name in self.in_progress_nodes[comp_name]:
             self.in_progress_nodes[comp_name].remove(func_name)
             logger.error(f"[{comp_name}] Task permanently failed: {func_name}. DAG halted for this branch.")
             
             # Escalate to Level 3 (Boss/Architect) to rethink the specification
             await bus.publish("Critical_Pipeline_Failure", payload, "DAGTracker")

# Initialize singleton
dag_tracker = DAGTracker()