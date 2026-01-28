"""
Planner Agent Schema - Minimal decomposition for multi-step PV tasks
"""

PLANNER_SCHEMA = {
    "task_type": {
        "type": "string",
        "enum": ["single_simulation", "comparison", "validation_only", "explanation"],
        "description": "High-level task category"
    },
    "reasoning": {
        "type": "string",
        "description": "Brief explanation of task decomposition rationale"
    },
    "subtasks": {
        "type": "array",
        "description": "Ordered list of atomic steps",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Unique subtask ID (A, B, C...)"},
                "action": {
                    "type": "string",
                    "enum": ["simulate", "compare", "validate", "explain"],
                    "description": "What to do"
                },
                "variant": {
                    "type": "object",
                    "description": "Simulation parameters that vary from base (for comparisons)",
                    "properties": {
                        "tilt": {"type": "number"},
                        "azimuth": {"type": "number"},
                        "tracking": {"type": "string"},
                        "temp_model": {"type": "string"},
                        "dc_ac_ratio": {"type": "number"}
                    }
                },
                "must_return": {
                    "type": "array",
                    "description": "Required output fields for this subtask",
                    "items": {"type": "string"}
                },
                "compare_on": {"type": "string", "description": "Field to compare (for action=compare)"},
                "winner_rule": {
                    "type": "string",
                    "enum": ["max", "min"],
                    "description": "How to choose winner (for action=compare)"
                }
            },
            "required": ["id", "action"]
        }
    },
    "final_schema": {
        "type": "string",
        "description": "Expected output schema name (single_sim_v1, comparison_v1, etc.)"
    },
    "base_assumptions": {
        "type": "object",
        "description": "Common parameters across all subtasks",
        "properties": {
            "dc_kw": {"type": "number"},
            "azimuth": {"type": "number"},
            "losses_pct": {"type": "number"},
            "location": {"type": "string"}
        }
    },
    "recovery_strategy": {
        "type": "object",
        "description": "Error handling ladder",
        "properties": {
            "on_tool_error": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered recovery steps for execution errors"
            },
            "on_schema_error": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Recovery for output formatting issues"
            }
        }
    }
}


PLANNER_PROMPT = """You are a PV simulation task planner. Your job is to decompose user requests into atomic, executable subtasks.

RULES:
1. Be minimal - only create subtasks that are necessary
2. For comparisons: create separate simulate subtasks for each variant, then one compare subtask
3. For single simulations: create one simulate subtask
4. For validation/error cases: create validate subtask with no tool execution
5. Always specify must_return fields for simulate subtasks
6. Always specify final_schema that matches expected output format

TASK TYPES:
- single_simulation: One PV calculation (annual energy, daily profile, etc.)
- comparison: Multiple simulations compared (tilt A vs B, tracker vs fixed)
- validation_only: Input validation without execution (invalid location, extreme params)
- explanation: No calculation, just explain concepts

SUBTASK ACTIONS:
- simulate: Run pvlib calculation with specific parameters
- compare: Deterministic comparison of simulate results (orchestrator handles this)
- validate: Check inputs without execution
- explain: Return explanation without calculation

RECOVERY STRATEGIES:
Common on_tool_error options:
- "switch_to_pvwatts": Use simpler PVWatts model instead of detailed ModelChain
- "reduce_timespan": Shorten simulation period (month instead of year)
- "simplify_model": Remove complex temperature/loss models
- "explicit_timezone": Force timezone specification
- "resample_hourly": Handle DST issues by resampling

Common on_schema_error options:
- "rerun_format_only": Re-extract data without recalculating
- "use_defaults": Fill missing fields with reasonable defaults

EXAMPLES:

User: "Calculate annual energy for 10 kW system in Sydney"
Plan:
{{
  "task_type": "single_simulation",
  "reasoning": "Single simulation request, no comparison needed",
  "subtasks": [
    {{"id": "A", "action": "simulate", "must_return": ["annual_kwh", "capacity_factor"]}}
  ],
  "final_schema": "single_sim_v1",
  "base_assumptions": {{"dc_kw": 10, "azimuth": 0, "losses_pct": 14, "location": "Sydney"}},
  "recovery_strategy": {{
    "on_tool_error": ["switch_to_pvwatts", "reduce_timespan"],
    "on_schema_error": ["rerun_format_only"]
  }}
}}

User: "Compare 30° vs 45° tilt in Sydney for 10 kW system"
Plan:
{{
  "task_type": "comparison",
  "reasoning": "Comparison task: need to simulate both tilt angles then compare results",
  "subtasks": [
    {{"id": "A", "action": "simulate", "variant": {{"tilt": 30}}, "must_return": ["annual_kwh"]}},
    {{"id": "B", "action": "simulate", "variant": {{"tilt": 45}}, "must_return": ["annual_kwh"]}},
    {{"id": "C", "action": "compare", "compare_on": "annual_kwh", "winner_rule": "max"}}
  ],
  "final_schema": "comparison_v1",
  "base_assumptions": {{"dc_kw": 10, "azimuth": 0, "losses_pct": 14, "location": "Sydney"}},
  "recovery_strategy": {{
    "on_tool_error": ["switch_to_pvwatts", "reduce_timespan"],
    "on_schema_error": ["rerun_format_only"]
  }}
}}

User: "Calculate energy at latitude 200°N"
Plan:
{{
  "task_type": "validation_only",
  "reasoning": "Invalid location parameters - reject without execution",
  "subtasks": [
    {{"id": "V", "action": "validate"}}
  ],
  "final_schema": "error_v1",
  "base_assumptions": {{"location": "invalid"}},
  "recovery_strategy": {{}}
}}

Now decompose this user request into a plan. Return ONLY valid JSON matching the schema above.

USER REQUEST: {user_prompt}
"""


def validate_plan(plan: dict) -> tuple[bool, str]:
    """Validate planner output against schema"""

    if "task_type" not in plan:
        return False, "Missing task_type"

    if plan["task_type"] not in ["single_simulation", "comparison", "validation_only", "explanation"]:
        return False, f"Invalid task_type: {plan['task_type']}"

    if "subtasks" not in plan or not plan["subtasks"]:
        return False, "Missing or empty subtasks"

    for st in plan["subtasks"]:
        if "id" not in st or "action" not in st:
            return False, f"Subtask missing id or action: {st}"

        if st["action"] not in ["simulate", "compare", "validate", "explain"]:
            return False, f"Invalid action: {st['action']}"

        # Validate simulate subtasks have must_return
        if st["action"] == "simulate" and "must_return" not in st:
            return False, f"Simulate subtask {st['id']} missing must_return"

        # Validate compare subtasks have compare_on and winner_rule
        if st["action"] == "compare":
            if "compare_on" not in st or "winner_rule" not in st:
                return False, f"Compare subtask {st['id']} missing compare_on or winner_rule"

    if "final_schema" not in plan:
        return False, "Missing final_schema"

    return True, "OK"
