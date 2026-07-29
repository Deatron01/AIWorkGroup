import asyncio
import json
import re
from typing import Dict, Any
from openai import AsyncOpenAI
from functools import partial
from tools.file_ops import write_file, read_file
from tools.sandbox_async import AsyncDockerSandbox
from tools.git import GitTransactionManager
from core.event_bus import EventBus
from core.hitl_manager import hitl_manager
from core.dag_tracker import DAGTracker
from core.schemas import TaskGraph, TaskNode
import ast

# Initialize external clients and tools
client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="local")
sandbox = AsyncDockerSandbox("./workspace")
git_manager = GitTransactionManager("./workspace")

class AsyncWorkerNode:
    def __init__(self, bus: EventBus, worker_model: str = "qwen2.5-coder:14b-instruct-q8_0", supervisor_model: str = "gemma2:27b"):
        self.bus = bus
        self.worker_model = worker_model
        self.supervisor_model = supervisor_model

    async def handle_ready_task(self, payload: Dict[str, Any]):
        task = payload["task"]
        
        # Safely extract attributes whether `task` is a dict or a Pydantic object
        if isinstance(task, dict):
            task_id = task.get("task_id")
            description = task.get("description")
            file_path = task.get("file_path")
        else:
            task_id = getattr(task, "task_id", None)
            description = getattr(task, "description", None)
            file_path = getattr(task, "file_path", None)

        loop = asyncio.get_running_loop()
        
        # 1. Start a fresh Git Worktree for the task and capture its path
        worktree_path = await loop.run_in_executor(None, git_manager.start_task_branch, task_id)
        
        # 2. Run the agent's work loop, passing the isolated path
        success = await self._run_llm_retry_loop(task, worktree_path)

        # 3. Finalize the task based on the result
        if success:
            commit_msg = f"Completed {task_id}: {description}"
            try:
                # Pass worktree_path to commit_and_merge to target the correct folder
                await loop.run_in_executor(None, git_manager.commit_and_merge, task_id, commit_msg, worktree_path)
                await self.bus.publish("task.completed", {"task_id": task_id})
            except RuntimeError as e:
                print(f"[Worker] Error finalizing task: {e}")
                await self.bus.publish("task.failed", {"task_id": task_id, "reason": "merge_conflict"})
        else:
            await self.bus.publish("task.failed", {"task_id": task_id, "reason": "max_retries"})

    async def fix_code(self, original_task: str, broken_code: str, error_log: str) -> str:
        sys_prompt = (
            "You are an expert Python debugger. The code you wrote failed its unit tests. "
            "Analyze the provided error log and rewrite the code to fix the exact issue. "
            "Output ONLY the raw, corrected Python code. Do not include markdown formatting, "
            "explanations, or conversational text."
        )
        
        user_content = (
            f"Task: {original_task}\n\n"
            f"BROKEN CODE:\n{broken_code}\n\n"
            f"ERROR LOG:\n{error_log}"
        )
        
        response = await client.chat.completions.create(
            model=self.worker_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1,
            extra_body={"options": {"num_ctx": 16384}}
        )
        raw_output = response.choices[0].message.content
        return raw_output.replace("```python", "").replace("```", "").strip()
    
    async def _run_llm_retry_loop(self, task, worktree_path: str, max_retries: int = 5) -> bool:
        if isinstance(task, dict):
            task_id = task.get("task_id")
            description = task.get("description")
            file_path = task.get("file_path")
        else:
            task_id = getattr(task, "task_id", None)
            description = getattr(task, "description", None)
            file_path = getattr(task, "file_path", None)

        # Dynamically bind the worktree_path to the file operation tools
        worker_write_file = partial(write_file, base_path=worktree_path)
        worker_read_file = partial(read_file, base_path=worktree_path)

        attempt = 1
        current_prompt = f"{description}\n\nYou MUST use the write_file tool to save your work. Do not output code in conversational markdown."
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write code or text to a file in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "The name of the file, e.g., 'fibonacci.py'"
                            },
                            "content": {
                                "type": "string",
                                "description": "The exact code to write into the file"
                            }
                        },
                        "required": ["filename", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of an existing file in the workspace. Use this to inspect code before modifying it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "The name of the file to read, e.g., 'src/main.py'"
                            }
                        },
                        "required": ["filename"]
                    }
                }
            }
        ]
        
        while attempt <= max_retries:
            print(f"[Worker] Executing task {task_id} (Attempt {attempt})...")
            
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an elite autonomous coding agent. "
                        "You must ONLY communicate by executing the provided tools (like write_file or read_file). "
                        "Never output code in conversational markdown. Always use the tools to write files."
                    )
                },
                {"role": "user", "content": current_prompt}
            ]
            task_completed = False
            
            # --- LLM GENERATION PHASE ---
            try:
                while not task_completed:
                    response = await client.chat.completions.create(
                        model=self.worker_model,
                        messages=messages, 
                        tools=tools,
                        temperature=0.1,
                        extra_body={
                            "options": {
                                "num_ctx": 16384
                            }
                        }
                    )
                    
                    message = response.choices[0].message
                    messages.append(message) 
                    
                    if message.tool_calls:
                        for tool_call in message.tool_calls:
                            
                            # --- WRITE FILE ---
                            if tool_call.function.name == "write_file":
                                args = json.loads(tool_call.function.arguments)
                                loop = asyncio.get_running_loop()
                                # Use the bound worker_write_file
                                result = await loop.run_in_executor(None, worker_write_file, args["filename"], args["content"])
                                print(f"[Worker] {result}")
                                task_completed = True
                                
                            # --- READ FILE ---
                            elif tool_call.function.name == "read_file":
                                args = json.loads(tool_call.function.arguments)
                                filename = args.get("filename")
                                print(f"[Worker] Tool called: Reading {filename}...")
                                
                                loop = asyncio.get_running_loop()
                                # Use the bound worker_read_file
                                file_content = await loop.run_in_executor(None, worker_read_file, filename)
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": "read_file",
                                    "content": file_content
                                })
                                print(f"[Worker] Successfully read {filename}. Passing context back to LLM...")
                                
                    # 3. Fallback handling 
                    elif message.content and "write_file" in message.content:
                        print("[Worker] Native tool call missed. Falling back to text parsing...")
                        raw_text = message.content
                        
                        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
                        json_str = json_match.group(1) if json_match else raw_text.strip()
                        
                        try:
                            parsed_call = json.loads(json_str)
                            if parsed_call.get("name") == "write_file" and "arguments" in parsed_call:
                                args = parsed_call["arguments"]
                                filename = args.get("filename")
                                content = args.get("content", "")
                                
                                loop = asyncio.get_running_loop()
                                # Use the bound worker_write_file
                                result = await loop.run_in_executor(None, worker_write_file, filename, content)
                                print(f"[Worker] (Fallback) {result}")
                                task_completed = True
                            else:
                                print("[Worker] Text contained JSON, but not a valid write_file call.")
                                task_completed = True
                        except json.JSONDecodeError:
                            # 1. AST FALLBACK: Try evaluating it as a literal Python dictionary
                            try:
                                parsed_call = ast.literal_eval(json_str)
                                if parsed_call.get("name") == "write_file" and "arguments" in parsed_call:
                                    args = parsed_call["arguments"]
                                    filename = args.get("filename")
                                    content = args.get("content", "")
                                    
                                    loop = asyncio.get_running_loop()
                                    result = await loop.run_in_executor(None, worker_write_file, filename, content)
                                    print(f"[Worker] (AST Fallback) {result}")
                                    task_completed = True
                                else:
                                    raise ValueError("Parsed dictionary is not a write_file tool call.")
                            except Exception as ast_error:
                                # 2. BOUNCE BACK: If both JSON and AST fail, tell the LLM to fix it.
                                print("[Worker] Failed to parse output. Bouncing back to LLM...")
                                messages.append({
                                    "role": "user",
                                    "content": f"System Error: Failed to parse your output. Ensure you provide valid JSON or a strict Python dictionary. Error: {ast_error}"
                                })
                                # Notice we DO NOT set task_completed = True here, forcing a retry.

                    else:
                        print("[Worker] No tool calls or recognizable JSON found in output.")
                        messages.append({
                            "role": "user", 
                            "content": "System Error: You must use the write_file tool to output your code."
                        })
                        # Again, leave task_completed = False to force a retry

            except Exception as e:
                print(f"[Worker] LLM Generation error: {e}")
                break # Exit the loop if the API entirely crashes
            
            # --- SUPERVISOR VERIFICATION PHASE (AI AS A JUDGE) ---
            print(f"[Worker] Running AI Supervisor verification for task {task_id}...")
            
            try:
                loop = asyncio.get_running_loop()
                # 1. Grab the exact code changes the agent just made in the isolated worktree
                diff_output = await loop.run_in_executor(None, git_manager.get_diff, worktree_path)
                
                if not diff_output.strip():
                    supervisor_verdict = "No code was written. You must use the write_file tool to write code."
                    print("[Worker] AI Supervisor Verification: FAILED (Empty Diff)")
                else:
                    # 2. AI Code Review Prompt
                    sys_prompt = (
                        "You are a strict, expert Lead Software Engineer. Review the code diff generated by a junior developer.\n"
                        "Compare the CODE against the TASK DESCRIPTION.\n"
                        "Check for completeness, logical errors, missing imports, and syntax issues.\n"
                        "You MUST respond ONLY with a JSON object in this exact format:\n"
                        '{"passed": true, "feedback": "Code perfectly meets requirements."}\n'
                        "or\n"
                        '{"passed": false, "feedback": "Detailed explanation of what is wrong and exactly how to fix it."}'
                    )
                    
                    user_prompt = f"TASK DESCRIPTION:\n{description}\n\nCODE DIFF (Uncommitted Changes):\n{diff_output}"

                    # 3. Call the LLM to judge the code
                    review_response = await client.chat.completions.create(
                        model=self.supervisor_model,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.1,
                        extra_body={
                            "options": {
                                "num_ctx": 8192
                            }
                        }
                    )
                    
                    raw_review = review_response.choices[0].message.content
                    json_match = re.search(r'\{.*?\}', raw_review, re.DOTALL)
                    
                    if json_match:
                        verdict = json.loads(json_match.group(0))
                    else:
                        verdict = {"passed": False, "feedback": "System error: Reviewer failed to output JSON."}

                    # 4. Evaluate the AI's verdict
                    if verdict.get("passed") is True:
                        supervisor_verdict = "VERIFICATION_PASSED"
                        print("[Worker] AI Supervisor Verification: PASSED")
                    else:
                        supervisor_verdict = verdict.get("feedback", "AI review failed with no feedback.")
                        print(f"[Worker] AI Supervisor Verification: FAILED\nReason: {supervisor_verdict}")
                        
            except Exception as e:
                supervisor_verdict = f"AI Evaluation error: {e}"
                print(f"[Worker] {supervisor_verdict}")
            
            # --- FINAL RESOLUTION ---
            if supervisor_verdict == "VERIFICATION_PASSED":
                # (HITL approval block remains the same here)
                await self.bus.publish("task.awaiting_approval", {
                    "task_id": task_id,
                    "diff": diff_output
                })
                
                decision = {"is_approved": True, "feedback": ""}
                
                if decision["is_approved"]:
                    print(f"[Worker] Task {task_id} approved by human.")
                    return True
                else:
                    print(f"[Worker] Task {task_id} REJECTED by human.")
                    rejection_reason = f"Human Review Failed: {decision['feedback']}"
                    current_prompt = f"Your previous code was rejected. {rejection_reason}\nFix the issues using write_file."
            else:
                # Pass the AI Judge's feedback directly back into the worker's prompt for the next loop iteration
                current_prompt = (
                    f"Your previous attempt failed the Lead Engineer's code review.\n\n"
                    f"### LEAD ENGINEER FEEDBACK ###\n"
                    f"{supervisor_verdict}\n\n"
                    f"### ORIGINAL TASK REQUIREMENTS ###\n"
                    f"{description}\n\n" # Assuming 'description' holds your task instructions
                    f"Read the feedback carefully, fix the errors, and rewrite the ENTIRE file using the `write_file` tool. "
                    f"Ensure you name the file exactly as requested in the requirements."
                )

            print(f"[Worker] Rolling back changes for attempt {attempt}...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, git_manager.rollback_attempt, worktree_path)
            attempt += 1
                
        return False