import asyncio
import json
import re
from tools.file_ops import list_workspace, read_file, archive_workspace, write_file

class BossPlanner:
    def __init__(self, llm_client, model_name: str = "llama3.1:8b"):
        """
        llm_client: AsyncOpenAI instance pointing to Ollama (e.g., http://127.0.0.1:11434/v1)
        model_name: Local model to execute the architecture planning.
        """
        self.llm = llm_client
        self.model = model_name

    async def _call_llm(self, system_prompt: str, user_content: str, json_mode: bool = False) -> str:
        """Wrapper for OpenAI-compatible Ollama API call."""
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2
        }
        
        # Enforce JSON mode natively in Ollama/OpenAI API
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.llm.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def generate_requirements(self, user_prompt: str, project_context: str = "") -> str:
        sys_prompt = (
            "You are a Staff Systems Architect. Analyze the user's request and output a "
            "comprehensive Software Requirements Specification (SRS) in Markdown.\n\n"
            "You MUST include the following sections:\n"
            "1. **Executive Summary**: High-level overview of the system.\n"
            "2. **System Architecture Diagram**: A ```mermaid graph TD diagram illustrating the data flow between components.\n"
            "3. **Functional Requirements**: Detailed bullet points of exact behaviors, edge cases, and triggers.\n"
            "4. **API & Data Contracts**: Exact JSON schemas for all telemetry payloads, event bus messages, or REST endpoints.\n"
            "5. **Execution Loop & Concurrency**: Clear documentation on how the asyncio event loops, background tasks, and batching mechanisms will interact without blocking.\n"
            "6. **Non-Functional Requirements**: Performance constraints, logging standards, and error handling protocols."
        )
        if project_context:
            sys_prompt += (
                "\n\nYou are modifying an existing codebase. Here is the current state of the files. "
                "Ensure your new requirements integrate seamlessly with this existing code, or explicitly "
                "state what needs to be refactored:\n\n" + project_context
            )
        return await self._call_llm(sys_prompt, user_prompt)

    async def design_architecture(self, requirements: str) -> str:
        sys_prompt = (
            "You are a Lead Software Engineer mapping out a complex Python microservice. "
            "Based on the provided SRS, design the exact technical architecture. Output a Markdown document.\n\n"
            "For EACH required file, you MUST provide:\n"
            "- **File Path**: (e.g., `src/consumers/telemetry.py`)\n"
            "- **Purpose**: One concise sentence.\n"
            "- **Dependencies**: What other local modules this file needs to import.\n"
            "- **Class/Function Signatures**: Write out the exact Python interfaces (using `typing` module) but DO NOT write the implementation block. Use `pass` or `...`.\n"
            "- **Test Strategy**: Briefly outline what the corresponding pytest file must cover, specifically mentioning mock data and async fixtures.\n\n"
            "Ensure the architecture is strictly modular. No global state variables. All I/O must be asynchronous."
        )
        return await self._call_llm(sys_prompt, requirements)

    async def generate_dag(self, architecture: str) -> dict:
        sys_prompt = (
            "You are an expert technical project manager. Based on the provided architecture, "
            "break the project down into a strict JSON execution graph (DAG). "
            "IMPORTANT: If this is an update to an existing codebase, do not create tasks to rewrite files from scratch. "
            "Instead, create tasks instructing the worker to 'Refactor', 'Update', or 'Fix' specific existing files. "
            "The worker has a `read_file` tool, so you can explicitly instruct it to: 'Read existing main.py and add X feature.'\n\n"
            "the System Architecture into an execution graph. Output ONLY valid JSON matching this schema:\n\n"
            "{\n"
            '  "project_name": "string",\n'
            '  "tasks": [\n'
            "    {\n"
            '      "task_id": "unique string identifier",\n'
            '      "file_path": "exact relative path of the file to create",\n'
            '      "description": "Detailed instructions for this module",\n'
            '      "dependencies": ["array of task_ids required before this task"]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "RULES:\n"
            "1. Every distinct file in the architecture must have its own task.\n"
            "2. If a module imports another custom module, list that module's task_id in dependencies.\n"
            "3. Do not combine multiple files into one task.\n"
            "4. In the `description` field, you MUST include the exact Class/Function signatures and Data Contracts required for that specific file so the execution worker knows exactly what to implement."
        )
        
        raw_json = await self._call_llm(sys_prompt, architecture, json_mode=True)
        
        # Robust parsing for local models
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            # Fallback regex extraction if a local model adds rogue text
            match = re.search(r'\{.*\}', raw_json, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"[Boss] Failed to parse DAG JSON from response:\n{raw_json}")

    async def plan_project(self, raw_prompt: str) -> dict:
        """Runs the complete asynchronous multi-stage planning pipeline with Phase 0 Triage."""
        
        print("[Boss] Phase 0: Triaging Workspace...")
        existing_files = list_workspace()
        project_context = ""
        
        if existing_files:
            triage_prompt = (
                f"User Goal: {raw_prompt}\n"
                f"Existing files in workspace: {existing_files}\n\n"
                "Are these files related to the user's new goal, or is this a completely new project? "
                "Respond ONLY with a JSON object: {\"is_related\": true/false}"
            )
            
            try:
                # FIXED: Changed self.llm_client to self.llm and self.model_name to self.model
                response = await self.llm.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": triage_prompt}]
                )
                
                triage_decision = json.loads(response.choices[0].message.content)
                
                if not triage_decision.get("is_related"):
                    print("[Boss] Files unrelated. Archiving old project...")
                    archive_result = archive_workspace()
                    print(f"[Boss] {archive_result}")
                else:
                    print("[Boss] Files related. Reading current state...")
                    project_context = "### CURRENT CODEBASE STATE ###\n"
                    for file in existing_files:
                        content = read_file(file)
                        project_context += f"--- {file} ---\n{content}\n\n"
                        
            except (json.JSONDecodeError, Exception) as e:
                print(f"[Boss] Triage failed or parsed invalid JSON ({e}). Assuming new project and archiving...")
                archive_workspace()

        print("[Boss] Phase 1: Drafting Requirements Specification...")
        requirements = await self.generate_requirements(raw_prompt, project_context)
        # ADDED: Save Phase 1
        write_file("planning_phase1_srs.md", requirements)
        
        print("[Boss] Phase 2: Designing System Architecture...")
        architecture = await self.design_architecture(requirements)
        # ADDED: Save Phase 2
        write_file("planning_phase2_architecture.md", architecture)
        
        print("[Boss] Phase 3: Generating Task Graph...")
        dag_data = await self.generate_dag(architecture)
        # ADDED: Save Phase 3
        write_file("planning_phase3_dag.json", json.dumps(dag_data, indent=4))
        
        print("[Boss] Planning complete. Execution DAG generated successfully.")
        return {
            "requirements": requirements,
            "architecture": architecture,
            "dag": dag_data
        }