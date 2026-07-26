import asyncio

async def main():
    # 1. Initialize core system
    sandbox.start()
    bus = EventBus()
    
    # 2. Attach the UI Bridge
    broadcaster = UIBroadcaster(bus, manager)
    
    # 3. Start the Event Bus background task
    bus_task = asyncio.create_task(bus.run())
    
    # 4. Start the FastAPI server using Uvicorn programmatically
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    print("🚀 Foundry Backend Running on ws://127.0.0.1:8000/ws/ui")
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())