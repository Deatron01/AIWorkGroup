import json
from typing import List, Literal
from pydantic import BaseModel, Field

class TaskNode(BaseModel):
    task_id: str = Field(..., description="Unique alphanumeric ID for this task (e.g., 'task_1')")
    description: str = Field(..., description="Highly detailed instruction for the worker")
    role: Literal["programmer", "tester", "architect"] = Field(..., description="The specialist needed")
    dependencies: List[str] = Field(default_factory=list, description="List of task_ids that must be completed before this task starts")

class TaskGraph(BaseModel):
    project_name: str
    tasks: List[TaskNode]