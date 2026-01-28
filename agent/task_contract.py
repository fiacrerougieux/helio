"""
Task Contract v0.1 - First-class task specification and validation.

This module defines the schema and validation for PV simulation tasks,
promoting eval tasks to contracts that the planner/orchestrator must satisfy.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
import json
from pathlib import Path


class TaskType(Enum):
    """Task types defining execution patterns."""
    SINGLE = "single"          # Single simulation run
    COMPARISON = "comparison"  # Compare 2+ variants
    SWEEP = "sweep"           # Parameter sweep (find optimal)
    SENSITIVITY = "sensitivity"  # Sensitivity analysis


class ModelFamily(Enum):
    """PV modeling approach."""
    PVWATTS = "pvwatts"       # Simplified PVWatts model
    MODELCHAIN = "modelchain"  # Full pvlib ModelChain


@dataclass
class ValidationRule:
    """Validation bounds and invariants for outputs."""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    required: bool = True
    invariants: List[str] = field(default_factory=list)  # e.g., ["gain_percent > 0"]


@dataclass
class Variant:
    """A single configuration variant for comparison/sweep tasks."""
    name: str
    parameters: Dict[str, Any]  # e.g., {"tilt": 30, "azimuth": 0}
    description: Optional[str] = None


@dataclass
class ReductionSpec:
    """Specification for reducing multiple variant results into final output."""
    operation: Literal["compare", "find_optimal", "compute_sensitivity"]
    output_fields: List[str]  # Fields to extract from reduction
    comparison_metric: Optional[str] = None  # e.g., "daily_kwh" for comparisons
    optimal_criterion: Optional[str] = None  # e.g., "maximize" or "minimize"

    # Deterministic computation rules
    gain_formula: Optional[str] = None  # e.g., "(tracker - fixed) / fixed * 100"
    winner_rule: Optional[str] = None  # e.g., "max(daily_kwh)"


@dataclass
class TaskContract:
    """
    Task Contract v0.1 - Single source of truth for PV simulation tasks.

    Defines required inputs, expected outputs, validation rules, and execution strategy.
    """
    # Metadata
    id: str
    name: str
    description: str
    contract_version: str = "0.1"

    # Task classification
    task_type: TaskType = TaskType.SINGLE

    # Required inputs
    location: Dict[str, Any] = field(default_factory=dict)  # {lat, lon, timezone, name}
    datetime_spec: Dict[str, Any] = field(default_factory=dict)  # {date, start, end, freq}
    system_spec: Dict[str, Any] = field(default_factory=dict)  # {dc_capacity_kw, module, inverter}
    model_family: ModelFamily = ModelFamily.MODELCHAIN
    timestep: str = "1h"  # e.g., "1h", "15min"

    # Assumptions (explicit!)
    assumptions: Dict[str, Any] = field(default_factory=dict)  # losses, temp_model, albedo, etc.

    # For comparison/sweep/sensitivity tasks
    variants: List[Variant] = field(default_factory=list)
    reduction: Optional[ReductionSpec] = None

    # Expected outputs
    expected_schema: Dict[str, str] = field(default_factory=dict)  # {field: type}
    validation_rules: Dict[str, ValidationRule] = field(default_factory=dict)

    # Natural language query (for LLM)
    query: str = ""

    # Guidance for code generation
    hints: List[str] = field(default_factory=list)

    def validate_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate simulation output against contract rules.

        Returns:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str],
                "missing_fields": List[str]
            }
        """
        errors = []
        warnings = []
        missing_fields = []

        # Check schema completeness
        for field_name, field_type in self.expected_schema.items():
            if field_name not in output:
                if self.validation_rules.get(field_name, ValidationRule()).required:
                    missing_fields.append(field_name)
                continue

            # Type check (basic)
            value = output[field_name]
            if field_type == "float" and not isinstance(value, (int, float)):
                errors.append(f"{field_name}: expected float, got {type(value).__name__}")
            elif field_type == "int" and not isinstance(value, int):
                errors.append(f"{field_name}: expected int, got {type(value).__name__}")
            elif field_type == "str" and not isinstance(value, str):
                errors.append(f"{field_name}: expected str, got {type(value).__name__}")

        # Check validation rules
        for field_name, rule in self.validation_rules.items():
            if field_name not in output:
                continue

            value = output[field_name]

            # Bounds check
            if rule.min_value is not None and value < rule.min_value:
                errors.append(f"{field_name}={value} below minimum {rule.min_value}")
            if rule.max_value is not None and value > rule.max_value:
                errors.append(f"{field_name}={value} above maximum {rule.max_value}")

            # Invariants check (simple eval for now - could be more sophisticated)
            for invariant in rule.invariants:
                try:
                    # Create namespace with all output values
                    namespace = output.copy()
                    if not eval(invariant, {"__builtins__": {}}, namespace):
                        errors.append(f"Invariant failed: {invariant}")
                except Exception as e:
                    warnings.append(f"Could not evaluate invariant '{invariant}': {e}")

        return {
            "valid": len(errors) == 0 and len(missing_fields) == 0,
            "errors": errors,
            "warnings": warnings,
            "missing_fields": missing_fields
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "contract_version": self.contract_version,
            "task_type": self.task_type.value,
            "location": self.location,
            "datetime_spec": self.datetime_spec,
            "system_spec": self.system_spec,
            "model_family": self.model_family.value,
            "timestep": self.timestep,
            "assumptions": self.assumptions,
            "variants": [{"name": v.name, "parameters": v.parameters, "description": v.description}
                        for v in self.variants],
            "reduction": {
                "operation": self.reduction.operation,
                "output_fields": self.reduction.output_fields,
                "comparison_metric": self.reduction.comparison_metric,
                "optimal_criterion": self.reduction.optimal_criterion,
                "gain_formula": self.reduction.gain_formula,
                "winner_rule": self.reduction.winner_rule
            } if self.reduction else None,
            "expected_schema": self.expected_schema,
            "validation_rules": {
                name: {
                    "min": rule.min_value,
                    "max": rule.max_value,
                    "required": rule.required,
                    "invariants": rule.invariants
                } for name, rule in self.validation_rules.items()
            },
            "query": self.query,
            "hints": self.hints
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContract":
        """Deserialize contract from dictionary."""
        # Convert validation rules
        validation_rules = {}
        for name, rule_data in data.get("validation_rules", {}).items():
            validation_rules[name] = ValidationRule(
                min_value=rule_data.get("min"),
                max_value=rule_data.get("max"),
                required=rule_data.get("required", True),
                invariants=rule_data.get("invariants", [])
            )

        # Convert variants
        variants = []
        for v_data in data.get("variants", []):
            variants.append(Variant(
                name=v_data["name"],
                parameters=v_data["parameters"],
                description=v_data.get("description")
            ))

        # Convert reduction spec
        reduction = None
        if data.get("reduction"):
            r_data = data["reduction"]
            reduction = ReductionSpec(
                operation=r_data["operation"],
                output_fields=r_data["output_fields"],
                comparison_metric=r_data.get("comparison_metric"),
                optimal_criterion=r_data.get("optimal_criterion"),
                gain_formula=r_data.get("gain_formula"),
                winner_rule=r_data.get("winner_rule")
            )

        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            contract_version=data.get("contract_version", "0.1"),
            task_type=TaskType(data.get("task_type", "single")),
            location=data.get("location", {}),
            datetime_spec=data.get("datetime_spec", {}),
            system_spec=data.get("system_spec", {}),
            model_family=ModelFamily(data.get("model_family", "modelchain")),
            timestep=data.get("timestep", "1h"),
            assumptions=data.get("assumptions", {}),
            variants=variants,
            reduction=reduction,
            expected_schema=data.get("expected_schema", {}),
            validation_rules=validation_rules,
            query=data.get("query", ""),
            hints=data.get("hints", [])
        )

    def save(self, path: Path):
        """Save contract to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "TaskContract":
        """Load contract from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
