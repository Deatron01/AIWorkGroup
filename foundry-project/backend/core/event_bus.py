# foundry-project/backend/core/event_bus.py
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List

# Configure logging for observability
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EventBus")

@dataclass
class Event:
    """Represents a discrete message passed between AI microservices."""
    topic: str
    payload: Any  # This will strictly be Pydantic models from schemas.py
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

class EventBus:
    """
    Asynchronous message broker. Decouples the LLM agents to maximize parallelism
    and isolate failures.
    """
    def __init__(self):
        # Maps event topics to a list of async subscriber callback functions
        self._subscribers: Dict[str, List[Callable[[Event], Awaitable[None]]]] = {}
        # Stores a ledger of all events for rollback and debugging (The "Git" approach)
        self._event_ledger: List[Event] = []

    def subscribe(self, topic: str, handler: Callable[[Event], Awaitable[None]]) -> None:
        """Registers an asynchronous handler to listen for a specific event topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.info(f"Attached subscriber to topic: [{topic}]")

    async def publish(self, topic: str, payload: Any, source: str) -> None:
        """
        Emits an event to the bus. All subscribed agents will process the event
        concurrently via asyncio.create_task.
        """
        event = Event(topic=topic, payload=payload, source=source)
        self._event_ledger.append(event)
        logger.info(f"Published Event: [{topic}] from <{source}>")
        
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                # Fire-and-forget: execute the agent's task without blocking the bus
                asyncio.create_task(self._safe_invoke(handler, event))
        else:
            logger.warning(f"No subscribers listening for topic: [{topic}]")

    async def _safe_invoke(self, handler: Callable[[Event], Awaitable[None]], event: Event) -> None:
        """
        Executes the agent handler safely. Catches any unhandled agent crashes 
        and automatically escalates them as Level 1/Level 2 System Errors.
        """
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Agent execution failed on event [{event.topic}]: {str(e)}", exc_info=True)
            
            # Emit an internal failure event so the Supervisor (gemma2:27b) can intervene
            error_payload = {
                "failed_topic": event.topic,
                "original_source": event.source,
                "error_message": str(e)
            }
            # Recursively publish the error so the Supervisor can pick it up
            asyncio.create_task(
                self.publish("System_Error_Encountered", payload=error_payload, source="EventBus")
            )

# Instantiate a global singleton bus to be imported across the app
bus = EventBus()