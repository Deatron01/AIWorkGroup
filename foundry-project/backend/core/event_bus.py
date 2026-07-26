import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

@dataclass
class Event:
    topic: str
    payload: Dict[str, Any]

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.queue = asyncio.Queue()

    def subscribe(self, topic: str, callback: Callable):
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    async def publish(self, topic: str, payload: Dict[str, Any]):
        event = Event(topic=topic, payload=payload)
        await self.queue.put(event)
        # This is where you would also push the event to a UI WebSocket queue

    async def run(self):
        """Continuously processes events from the queue."""
        while True:
            event = await self.queue.get()
            if event.topic in self.subscribers:
                for callback in self.subscribers[event.topic]:
                    # Fire and forget callbacks as background tasks
                    asyncio.create_task(callback(event.payload))
            self.queue.task_done()