# foundry-project/backend/core/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class FunctionContract(BaseModel):
    """Emitted by the Function Designer. Dictates exactly what the Worker must build."""
    function_name: str = Field(..., description="Exact name of the function to be generated.")
    purpose: str = Field(..., description="Short explanation of what the function does.")
    parameters: Dict[str, str] = Field(..., description="Key-value mapping of parameter names to their data types.")
    return_type: str = Field(..., description="The exact return type of the function.")
    exceptions_raised: List[str] = Field(default_factory=list, description="Any exceptions this function is allowed to throw.")
    side_effects: str = Field(..., description="Allowed state mutations. Must be 'None' if purely functional.")
    thread_safety: str = Field(..., description="Requirement for concurrency (e.g., 'Requires Mutex', 'Stateless').")
    time_complexity_expectation: str = Field(..., description="Expected Big-O time complexity.")

class ComponentScope(BaseModel):
    """Emitted by the Component Planner. Contains multiple function contracts."""
    component_name: str
    description: str
    dependencies: List[str]
    functions: List[FunctionContract]

class ImplementationResult(BaseModel):
    """Emitted by the Worker AI after attempting to satisfy a FunctionContract."""
    function_name: str
    source_code: str = Field(..., description="The raw, unescaped code string.")
    imports_required: List[str] = Field(..., description="List of exact imports required for this snippet to compile.")
    compiles_successfully: bool = Field(..., description="Self-reported status before reaching the Unit Tester.")
    notes: Optional[str] = None

class RecoveryPlan(BaseModel):
    analysis: str = Field(..., description="Explanation of why the implementation failed based on the error logs.")
    revised_purpose: str = Field(..., description="A newly adjusted purpose/instruction to help the Worker succeed.")
    requires_architecture_change: bool = Field(..., description="True only if the component fundamentally cannot be built as requested.")

class SystemArchitecture(BaseModel):
    project_name: str
    description: str
    components: List[str] = Field(..., description="List of major module/component names to be built.")
    architecture_notes: str = Field(..., description="High-level rules, frameworks, or database choices.")