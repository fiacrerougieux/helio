from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field

class APICard(BaseModel):
    """
    Represents a specific API function/class that is allowed to be used.
    Used for strict enforcement of available tools for the SimAgent.
    """
    symbol: str = Field(..., description="Full dot-path symbol, e.g. 'pvlib.irradiance.get_total_irradiance'")
    import_stmt: str = Field(..., description="Import statement, e.g. 'from pvlib import irradiance'")
    callable_name: str = Field(..., description="Name to use in code, e.g. 'irradiance.get_total_irradiance'")
    kind: Literal['function', 'method', 'class'] = Field(..., description="Type of the callable")
    signature: str = Field(..., description="Canonical string signature from inspect.signature")
    doc: Optional[str] = Field(None, description="Short docstring snippet (1-3 lines)")
    examples: Optional[str] = Field(None, description="Minimal usage example")
    version: str = Field(..., description="Version of the library (e.g. pvlib 0.14.3)")

class NeedsList(BaseModel):
    """
    A list of symbols required to complete a specific task step.
    This is determined by the Planner/Router (via code mapping) and passed to DocsAgent.
    """
    symbols: List[str] = Field(..., description="List of full dot-path symbols needed")
    reason: Optional[str] = Field(None, description="Context for why these are needed")

class NeedAPIAction(BaseModel):
    """
    Action for SimAgent to request access to an API that is missing from its allowed cards.
    This triggers the DocsAgent to retrieve the card if valid.
    """
    action: Literal["need_api"] = "need_api"
    symbols: List[str] = Field(..., description="List of symbols the agent tried to use or needs")
    reason: str = Field(..., description="Why the agent believes it needs this API")
