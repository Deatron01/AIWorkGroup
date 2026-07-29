# foundry-project/backend/tools/model_manager.py
import json
import asyncio
from typing import Type, Any, Optional
from pydantic import BaseModel
import ollama

# Hardcoded model pipeline
BOSS_MODEL = "llama3.1:70b-instruct-q2_K"
WORKER_MODEL = "qwen2.5-coder:14b-instruct-q8_0"
SUPERVISOR_MODEL = "gemma2:27b"

class ModelManager:
    """
    Handles asynchronous API calls to the local Ollama instances, 
    enforcing Pydantic schemas via JSON mode for deterministic pipelines.
    """
    
    @staticmethod
    async def generate_structured_output(
        model_name: str, 
        prompt: str, 
        schema_model: Type[BaseModel],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1
    ) -> BaseModel:
        """
        Forces the LLM to output valid JSON matching the provided Pydantic schema.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        # Inject the schema into the prompt to guide the model's generation
        schema_json = schema_model.model_json_schema()
        instruction = (
            f"{prompt}\n\n"
            f"You MUST respond with RAW JSON that exactly matches this schema:\n"
            f"{json.dumps(schema_json, indent=2)}\n\n"
            "Do not include markdown blocks, greetings, or explanations. Just the JSON."
        )
        messages.append({"role": "user", "content": instruction})

        client = ollama.AsyncClient()
        response = await client.chat(
            model=model_name,
            messages=messages,
            format="json",
            options={"temperature": temperature} 
        )

        raw_content = response['message']['content']
        
        try:
            # Parse and validate the response against the exact Pydantic schema
            parsed_data = json.loads(raw_content)
            return schema_model.model_validate(parsed_data)
            
        except json.JSONDecodeError as e:
            # In our event bus, this will trigger a localized Level 1 Retry
            raise ValueError(f"[{model_name}] failed to return valid JSON. Payload: {raw_content}") from e
        except Exception as e:
            raise ValueError(f"[{model_name}] Schema validation failed: {str(e)}") from e

    @classmethod
    async def run_boss(cls, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        return await cls.generate_structured_output(
            model_name=BOSS_MODEL,
            prompt=prompt,
            schema_model=schema,
            system_prompt="You are the Chief Software Architect. You define systems but never write implementation logic.",
            temperature=0.3 # Slightly higher for architectural creativity
        )

    @classmethod
    async def run_worker(cls, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        return await cls.generate_structured_output(
            model_name=WORKER_MODEL,
            prompt=prompt,
            schema_model=schema,
            system_prompt="You are a precise implementation specialist. You satisfy function contracts exactly as requested.",
            temperature=0.0 # Zero temperature for maximum deterministic syntax
        )

    @classmethod
    async def run_supervisor(cls, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        return await cls.generate_structured_output(
            model_name=SUPERVISOR_MODEL,
            prompt=prompt,
            schema_model=schema,
            system_prompt="You are a strict, senior code reviewer looking for edge cases, memory leaks, and logic flaws.",
            temperature=0.1
        )