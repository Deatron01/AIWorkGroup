import httpx
from openai import AsyncOpenAI

class ModelManager:
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host
        self.generate_endpoint = f"{self.host}/api/generate"
        self.llm = AsyncOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )

    async def unload_model(self, model_name: str):
        """Forces Ollama to drop the model from VRAM."""
        print(f"[ModelManager] Unloading '{model_name}' from VRAM...")
        async with httpx.AsyncClient() as client:
            try:
                # Setting keep_alive to 0 immediately unloads the model
                await client.post(self.generate_endpoint, json={
                    "model": model_name,
                    "keep_alive": 0
                })
                print(f"[ModelManager] Successfully unloaded '{model_name}'.")
            except Exception as e:
                print(f"[ModelManager] Failed to unload model: {e}")

    async def preload_model(self, model_name: str):
        try:
            print(f"[ModelManager] Pre-loading '{model_name}' into VRAM...")
            # Send a tiny prompt to force Ollama to load the model into VRAM
            await self.llm.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1
            )
            print(f"[ModelManager] Successfully preloaded '{model_name}'.")
        except Exception as e:
            print(f"[ModelManager] Failed to preload model: {e}")

    async def switch_models(self, model_to_unload: str, model_to_load: str):
        """Convenience method to swap models efficiently."""
        if model_to_unload:
            await self.unload_model(model_to_unload)
        if model_to_load:
            await self.preload_model(model_to_load)