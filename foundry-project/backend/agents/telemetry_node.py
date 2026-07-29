from tools.event_bus import event_bus
from api.dashboard_app import manager
import asyncio

async def telemetry_listener(event_type: str, data: dict):
    """
    Subscribes to ALL factory events and forwards them to the UI.
    """
    payload = {
        "event_type": event_type,
        "payload": data,
        "timestamp": data.get("timestamp")
    }
    # Push to all connected browser clients
    await manager.broadcast(payload)

def attach_telemetry():
    # Wildcard subscription or explicitly subscribe to all known topics
    event_bus.subscribe("Code_Generated", telemetry_listener)
    event_bus.subscribe("Agent_Log", telemetry_listener)
    event_bus.subscribe("Hardware_Metrics", telemetry_listener)
    event_bus.subscribe("Pipeline_State_Change", telemetry_listener)