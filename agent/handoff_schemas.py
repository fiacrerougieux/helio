from typing import Literal, List, Optional, Dict, Union, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError

# --- Base Contract ---

class BaseMessage(BaseModel):
    """Base class for all agent messages using strict validation."""
    contract_version: Literal["v1.0"] = "v1.0"
    model_config = ConfigDict(extra="forbid")

# --- Value Objects & Invariants ---

class PVLocation(BaseMessage):
    latitude: float = Field(..., description="Latitude in decimal degrees (-90 to 90)")
    longitude: float = Field(..., description="Longitude in decimal degrees (-180 to 180)")
    name: Optional[str] = Field(None, description="Human readable name of the location")

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not (-90 <= v <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not (-180 <= v <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return v

class PVSpec(BaseMessage):
    """Specification for basic PV system parameters."""
    system_capacity_kw: float = Field(..., description="DC system capacity in kW")
    tilt: float = Field(..., description="Panel tilt in degrees (0 horizontal, 90 vertical)")
    azimuth: float = Field(..., description="Panel azimuth in degrees (0=North, 90=East, 180=South, 270=West)")
    module_type: Literal["standard", "premium", "thin_film"] = "standard"
    array_type: Literal["fixed_open_rack", "roof_mount", "tracker"] = "fixed_open_rack"

    @field_validator("system_capacity_kw")
    @classmethod
    def validate_capacity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("System capacity must be positive")
        if v > 100000: # 100 MW limit for sanity
             raise ValueError("System capacity unusually large (>100MW), please verify")
        return v

    @field_validator("tilt")
    @classmethod
    def validate_tilt(cls, v: float) -> float:
        if not (0 <= v <= 90):
            raise ValueError("Tilt must be between 0 and 90 degrees")
        return v
    
    @field_validator("azimuth")
    @classmethod
    def validate_azimuth(cls, v: float) -> float:
        if not (0 <= v <= 360):
            raise ValueError("Azimuth must be between 0 and 360")
        return v

# --- Router Definitions ---

class RouterOutput(BaseMessage):
    """Output from the Router Agent."""
    route: Literal["simulate", "explain", "acknowledge", "unknown"] = Field(..., description="The type of action to take")
    task_type: Optional[str] = Field(None, description="Specific task type for simulation (e.g., 'annual_yield', 'daily_curve')")
    period: Optional[str] = Field(None, description="Time period for the simulation")
    reasoning: str = Field(..., description="Brief explanation of the routing decision")
    needs_python: bool = Field(False, description="Whether Python code execution is required")
    notes: List[str] = Field(default_factory=list, description="Any clarifications or assumptions")

    @field_validator("route")
    @classmethod
    def validate_route_dependencies(cls, v: str, info: Any) -> str:
        # Pydantic v2 validation context access is different, but simple check:
        # Logic relying on other fields is complex in validators, keeping simple for now.
        return v

# --- Action Definitions (SimAgent) ---

class PythonAction(BaseMessage):
    action: Literal["python"] = "python"
    code: str = Field(..., description="Valid Python code to execute. Must print valid JSON to stdout.")
    reasoning: Optional[str] = Field(None, description="Why this code is being generated")

class FinalAction(BaseMessage):
    action: Literal["final"] = "final"
    text: str = Field(..., description="Natural language response to the user")
    summary: Dict[str, Any] = Field(..., description="Structured summary of results")

class ErrorAction(BaseMessage):
    action: Literal["error"] = "error"
    message: str = Field(..., description="Error message description")

class NeedAPIAction(BaseMessage):
    action: Literal["need_api"] = "need_api"
    symbols: List[str] = Field(..., description="List of symbols the agent tried to use or needs")
    reason: str = Field(..., description="Why the agent believes it needs this API")

# Discriminated Union for Agent Actions
AgentAction = Union[PythonAction, FinalAction, ErrorAction, NeedAPIAction]

# --- QA Definitions ---

class QAIssue(BaseMessage):
    type: Literal["query_mismatch", "api_error", "physics_error", "missing_data", "schema", "physics", "runtime", "other"]
    severity: Optional[Literal["critical", "warning"]] = None
    description: str
    fix_suggestion: Optional[str] = None

class QAVerdict(BaseMessage):
    verdict: Literal["ok", "fix", "fail"]
    reasoning: str
    issues: List[QAIssue] = Field(default_factory=list)
    next: Optional[Literal["finalise", "revise_code"]] = None

