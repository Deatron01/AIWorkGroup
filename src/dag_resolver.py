def run_orchestrated_pipeline(user_goal: str):
    print("=== Starting Foundry Phase 3: Orchestration ===")
    sandbox.start()
    
    try:
        boss = BossAgent()
        plan = boss.plan(user_goal)
        
        completed_tasks = set()
        task_dict = {t.task_id: t for t in plan.tasks}
        
        # Keep looping until all tasks are in the completed set
        while len(completed_tasks) < len(plan.tasks):
            # Find all tasks whose dependencies are fully met AND aren't completed yet
            ready_tasks = [
                task for task in plan.tasks 
                if task.task_id not in completed_tasks 
                and all(dep in completed_tasks for dep in task.dependencies)
            ]
            
            if not ready_tasks:
                raise RuntimeError("Deadlock detected: No tasks ready but plan is incomplete. Check DAG logic.")

            # In Phase 3, we execute sequentially. 
            # (In Phase 4, we will dispatch these ready_tasks to an async event bus for parallel execution).
            for task in ready_tasks:
                print(f"\n>>> [Orchestrator] Starting Task: {task.task_id} ({task.role})")
                print(f">>> Description: {task.description}")
                
                # Setup specialized worker based on the role the Boss assigned
                worker_prompt = f"You are a senior {task.role}. Write complete, well-commented code/text. When editing existing files, you MUST use the `edit_file` tool.Follow these strict rules for {edit_file}:1. Your `search_block` must be an EXACT match to the existing file. Do not skip lines or alter indentation.2. If you are changing a single line inside a loop or function, include the `def` or `for` line in your `search_block` to ensure the block is unique.3. If the tool returns an error stating the block is not found, use `tool_read_file_chunk` to read the exact lines from the file, then try again."
                worker = LocalAgent(name=f"Worker-{task.task_id}", system_prompt=worker_prompt, tools=TOOLS)
                
                # Reuse the Phase 2 Supervisor logic
                supervisor = LocalAgent(
                    name="Supervisor",
                    system_prompt=(
                        "You are a strict QA Supervisor. Test the code provided to you using execute_bash. "
                        "If it meets the requirements, reply with 'VERIFICATION_PASSED'. "
                        "If it fails, reply with 'VERIFICATION_FAILED' followed by details."
                    ),
                    tools=TOOLS
                )
                
                # Execute the Task Loop (Worker writes -> Supervisor checks)
                execute_task_loop(worker, supervisor, task.description)
                
                # Mark as complete to unblock downstream dependencies
                completed_tasks.add(task.task_id)
                print(f"\n✅ Task {task.task_id} fully verified and completed!")

        print(f"\n🎉 Project '{plan.project_name}' completed successfully!")
        
    finally:
        sandbox.stop()

def execute_task_loop(worker: LocalAgent, supervisor: LocalAgent, task_description: str, max_retries: int = 3):
    """The Phase 2 retry loop, extracted into a standalone function."""
    attempt = 1
    current_prompt = task_description
    
    while attempt <= max_retries:
        print(f"\n--- ATTEMPT {attempt}/{max_retries} ---")
        worker.chat(current_prompt)
        
        supervisor_prompt = (
            f"The worker just attempted: '{task_description}'. "
            "Please verify their work using your execute_bash tool."
        )
        verdict = supervisor.chat(supervisor_prompt)
        
        if "VERIFICATION_PASSED" in verdict.upper():
            return True
        else:
            print("\n❌ Verification failed. Reworking...")
            current_prompt = f"Your previous attempt failed. Supervisor feedback: {verdict}\nFix the issues."
            attempt += 1
            
    raise RuntimeError("Task failed after maximum retries. Human intervention required.")