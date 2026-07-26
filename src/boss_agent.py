class BossAgent:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        # We inject the Pydantic JSON schema directly into the prompt
        self.schema_str = TaskGraph.model_json_schema()
        
        self.system_prompt = (
            "You are a Lead AI Systems Architect. Your job is to break down complex user requests "
            "into a structured Directed Acyclic Graph (DAG) of discrete tasks. "
            "Assign each task to a specific worker role (programmer, tester, architect). "
            "Ensure dependencies are logical (e.g., tests should be written after or alongside code, "
            "and files must be created before they are executed).\n\n"
            "You MUST output valid JSON that strictly matches this JSON schema:\n"
            f"{json.dumps(self.schema_str, indent=2)}"
        )

    def plan(self, user_goal: str) -> TaskGraph:
        print("\n[Boss] Analyzing request and building execution graph...")
        
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Create a project plan for this goal: {user_goal}"}
            ],
            response_format={"type": "json_object"}, # Forces JSON output
            temperature=0.1 # Very low temp for structural stability
        )
        
        raw_json = response.choices[0].message.content
        try:
            # Validate and parse the LLM output into our Pydantic objects
            graph = TaskGraph.model_validate_json(raw_json)
            print(f"[Boss] Successfully generated plan: {graph.project_name} with {len(graph.tasks)} tasks.")
            return graph
        except Exception as e:
            print(f"[Boss] Validation Error on output:\n{raw_json}")
            raise RuntimeError(f"Boss agent failed to produce valid schema: {e}")