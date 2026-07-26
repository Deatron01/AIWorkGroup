import os
import json
import subprocess
from typing import List, Dict, Any
from openai import OpenAI
from sandbox_manager_class import DockerSandbox

# ---------------------------------------------------------
# 1. Inference Engine Configuration
# ---------------------------------------------------------
# Defaulting to standard Ollama / vLLM local port
LOCAL_API_BASE = "http://localhost:11434/v1"
MODEL_NAME = "qwen2.5-coder:7b" # Adjust to your loaded model
WORKSPACE_DIR = "./workspace"

# Ensure workspace exists
os.makedirs(WORKSPACE_DIR, exist_ok=True)

client = OpenAI(
    base_url=LOCAL_API_BASE,
    api_key="local-execution-only" 
)

# ---------------------------------------------------------
# 2. Tool Definitions & Executors
# ---------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes content to a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the file (e.g., script.py)"},
                    "content": {"type": "string", "description": "The full code or text to write"}
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_bash",
            "description": "Executes a bash command inside the secure Docker sandbox. Use this to run scripts, tests, or linters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run (e.g., 'python script.py' or 'pytest -v')"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edits an existing file by replacing a specific block of text with a new block of text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The file to edit (e.g., src/main.py)"},
                    "search_block": {"type": "string", "description": "The EXACT lines of code to remove. Must include exact indentation and be unique in the file."},
                    "replace_block": {"type": "string", "description": "The new lines of code to insert in place of the search_block."}
                },
                "required": ["filename", "search_block", "replace_block"]
            }
        }
    } 
]

sandbox = DockerSandbox(WORKSPACE_DIR)
def tool_edit_file(filename: str, search_block: str, replace_block: str) -> str:
    """Replaces a targeted block of text safely."""
    filepath = os.path.join(WORKSPACE_DIR, filename)
    
    if not os.path.exists(filepath):
        return f"Error: File '{filename}' does not exist. Use write_file to create it first."

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Normalize line endings to prevent OS-level mismatch errors
    content = content.replace("\r\n", "\n")
    search_block = search_block.replace("\r\n", "\n")
    replace_block = replace_block.replace("\r\n", "\n")

    # Safety Check 1: Does the block exist?
    if search_block not in content:
        # Fallback: Try stripping leading/trailing whitespace in case the LLM added an extra newline
        if search_block.strip() in content:
            return "Error: Search block found, but whitespace/newlines didn't match exactly. Ensure you include the exact leading indentation."
        return (
            "Error: search_block not found in file. "
            "You must copy the lines EXACTLY as they appear in the file, including indentation. "
            "Use tool_read_file_chunk if you need to check the exact text."
        )

    # Safety Check 2: Is the block unique?
    occurrences = content.count(search_block)
    if occurrences > 1:
        return (
            f"Error: search_block matches {occurrences} places in the file. "
            "Please include more lines of context before or after your target lines to make the search_block unique."
        )

    # Apply the edit
    new_content = content.replace(search_block, replace_block)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    return f"Successfully edited {filename}. Replaced {len(search_block.splitlines())} lines with {len(replace_block.splitlines())} lines."
def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """Routes the tool call to the actual local execution logic."""

    if name == "write_file":
        filepath = os.path.join(WORKSPACE_DIR, args["filename"])
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(args["content"])
        return f"Successfully wrote {len(args['content'])} bytes to {args['filename']}."
    
    elif name == "execute_bash":
        return sandbox.execute(args["command"])
    
    elif name == "run_python_script":
        filepath = os.path.join(WORKSPACE_DIR, args["filename"])
        if not os.path.exists(filepath):
            return f"Error: {args['filename']} does not exist."
        
        try:
            # Note: In Phase 2, this moves into the Docker container.
            # Using subprocess locally for MVP.
            result = subprocess.run(
                ["python", filepath], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            return output if output else "Execution successful with no output."
        except subprocess.TimeoutExpired:
            return "Error: Script execution timed out."
        except Exception as e:
            return f"Error executing script: {str(e)}"
    
    return f"Error: Unknown tool {name}"

# ---------------------------------------------------------
# 3. Agent Wrapper
# ---------------------------------------------------------
class LocalAgent:
    def __init__(self, name: str, system_prompt: str, tools: List[Dict]):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.history = [{"role": "system", "content": system_prompt}]

    def chat(self, user_message: str) -> str:
        """Sends a message, handles tool calls recursively, and returns the final response."""
        self.history.append({"role": "user", "content": user_message})
        print(f"\n[{self.name}] Thinking...")

        while True:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=self.history,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.2 # Low temperature for more deterministic coding
            )
            
            message = response.choices[0].message
            self.history.append(message)

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    
                    print(f"[{self.name}] Tool Call: {func_name}({func_args})")
                    tool_result = execute_tool(func_name, func_args)
                    print(f"[{self.name}] Tool Result: {tool_result}")
                    
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": tool_result
                    })
                # Loop back to let the LLM process the tool results
            else:
                # No more tool calls, return final text
                final_text = message.content or ""
                print(f"[{self.name}] Final Response:\n{final_text}")
                return final_text

# ---------------------------------------------------------
# 4. Orchestration Loop (The Single Loop MVP)
# ---------------------------------------------------------
def run_mvp_loop():
    print("=== Starting Foundry MVP Phase 2 ===")
    
    # Start the Docker sandbox
    sandbox.start()
    
    try:
        # Initialize Agents (Worker and Supervisor code remains exactly the same)
        worker = LocalAgent(
            name="Worker",
            system_prompt="You are a senior software engineer. Write complete, well-commented Python code. Use the write_file tool to save your work.",
            tools=TOOLS
        )
        
        supervisor = LocalAgent(
            name="Supervisor",
            system_prompt=(
                "You are a strict QA Supervisor. You must test the code provided to you using execute_bash. "
                "Analyze the output. If it meets the requirements and runs without errors, reply with 'VERIFICATION_PASSED'. "
                "If it fails or outputs errors, reply with 'VERIFICATION_FAILED' followed by a detailed explanation."
            ),
            tools=TOOLS
        )

        task_description = "Write a python script called fizzbuzz.py that prints fizzbuzz for numbers 1 to 20. Then write a separate script test_fizzbuzz.py that imports it and tests it."
        max_retries = 3
        attempt = 1

        while attempt <= max_retries:
            print(f"\n--- ATTEMPT {attempt}/{max_retries} ---")
            
            worker_prompt = f"Task: {task_description}\nIf this is a retry, please fix the previously identified errors."
            worker.chat(worker_prompt)
            
            supervisor_prompt = (
                f"The worker has attempted the task: '{task_description}'. "
                "Use execute_bash to run 'python test_fizzbuzz.py' or 'python fizzbuzz.py' to verify it works."
            )
            supervisor_verdict = supervisor.chat(supervisor_prompt)
            
            if "VERIFICATION_PASSED" in supervisor_verdict.upper():
                print("\n✅ Task completed and verified successfully!")
                break
            else:
                print("\n❌ Verification failed. Sending back to worker...")
                task_description = f"Your previous code failed. Supervisor feedback: {supervisor_verdict}"
                attempt += 1

    finally:
        # Guarantee cleanup
        sandbox.stop()

if __name__ == "__main__":
    run_mvp_loop()