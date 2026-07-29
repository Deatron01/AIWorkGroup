import subprocess
import httpx
import sys
import asyncio

# The exact models required for the No-Compromise architecture
REQUIRED_MODELS = [
    "llama3.1:70b-instruct-q2_K",
    "qwen2.5-coder:14b-instruct-q8_0",
    "gemma2:27b"
]

OLLAMA_HOST = "http://127.0.0.1:11434"

async def ensure_models_loaded():
    print("[Startup] Checking Ollama environment...")
    
    # 1. Verify Ollama is running and fetch installed models
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            response.raise_for_status()
            data = response.json()
            
            # Extract names (e.g., "gemma2:27b") from the API response
            installed_models = [model.get("name") for model in data.get("models", [])]
            
    except httpx.RequestError:
        print("[Error] Could not connect to Ollama. Is the Ollama app running?")
        sys.exit(1)

    # 2. Compare required models against installed models
    for model in REQUIRED_MODELS:
        if model in installed_models:
            print(f"[Startup] OK: '{model}' is already installed.")
        else:
            print(f"[Startup] MISSING: '{model}'. Initiating automatic pull...")
            try:
                # Using subprocess allows us to see the native Ollama progress bar in the console
                subprocess.run(["ollama", "pull", model], check=True)
                print(f"[Startup] Successfully downloaded '{model}'.\n")
            except subprocess.CalledProcessError as e:
                print(f"[Error] Failed to pull '{model}'. Check your network connection. Details: {e}")
                sys.exit(1)
                
    print("[Startup] All required LLMs are present. Handing over to backend...")