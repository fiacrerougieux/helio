"""
Planner Agent - Decomposes tasks into executable subtasks.

The Planner analyzes task contracts and creates execution plans:
- SINGLE tasks → 1 simulation subtask
- COMPARISON tasks → N simulation subtasks (1 per variant) + 1 reduction
- SWEEP tasks → N simulation subtasks + 1 reduction
- SENSITIVITY tasks → N simulation subtasks + 1 reduction
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from agent.task_contract import TaskContract, TaskType, Variant
from agent.schemas.pv_spec_schema import CanonicalPVSpec
import logging


@dataclass
class Subtask:
    """A single simulation or reduction subtask."""
    id: str
    type: str  # "simulate" or "reduce"
    variant: Optional[Variant] = None
    pv_spec: Optional[CanonicalPVSpec] = None  # For simulate subtasks
    description: str = ""
    needs: List[str] = field(default_factory=list)  # List of API symbols required


@dataclass
class ExecutionPlan:
    """
    Execution plan for a task contract.

    Decomposes task into subtasks that the orchestrator executes sequentially/parallel.
    """
    contract_id: str
    subtasks: List[Subtask] = field(default_factory=list)
    needs_reduction: bool = False
    reduction_depends_on: List[str] = field(default_factory=list)  # Subtask IDs

    def add_subtask(self, subtask: Subtask):
        """Add subtask to plan."""
        self.subtasks.append(subtask)

    def get_simulate_subtasks(self) -> List[Subtask]:
        """Get all simulation subtasks."""
        return [st for st in self.subtasks if st.type == "simulate"]

    def get_reduction_subtask(self) -> Optional[Subtask]:
        """Get reduction subtask if present."""
        reduction_tasks = [st for st in self.subtasks if st.type == "reduce"]
        return reduction_tasks[0] if reduction_tasks else None


class PlannerAgent:
    """
    Decomposes task contracts into executable subtasks.

    For COMPARISON/SWEEP/SENSITIVITY tasks:
    1. Creates one "simulate" subtask per variant
    2. Creates one "reduce" subtask that depends on all simulations
    3. Each simulate subtask gets a modified CanonicalPVSpec with variant params

    This ensures:
    - Consistent simulation structure (all use same base spec)
    - Deterministic reduction (no LLM schema invention)
    - Clear dependency graph
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def _resolve_dependencies(self, pv_spec: CanonicalPVSpec) -> List[str]:
        """
        Resolve the list of PVLib API symbols needed to execute this spec.
        This provides the NeedsList for the DocsAgent.
        """
        # Core essentials for almost every PV task
        needs = [
            "pvlib.location.Location",
            "pvlib.pvsystem.PVSystem",
            "pvlib.modelchain.ModelChain",
            "pvlib.modelchain.ModelChain.run_model",
            "pandas.date_range",
            "pandas.Timestamp",
        ]

        # Tracking check
        if pv_spec.system.tracker_mode and pv_spec.system.tracker_mode != 'fixed':
            needs.append("pvlib.tracking.singleaxis")

        # Temperature check (if specific models are requested or just for robustness)
        needs.extend([
             "pvlib.temperature.saim_h",
             "pvlib.temperature.pvsyst_cell",
             "pvlib.temperature.faiman"
        ])

        # Inverter/Module (PVWatts is our default fallback/baseline)
        needs.extend([
            "pvlib.pvsystem.pvwatts_dc",
            "pvlib.inverter.pvwatts",
            "pvlib.pvsystem.retrieve_sam", # Useful for getting CEC parameters if needed
        ])

        # Irradiance
        needs.extend([
            "pvlib.irradiance.get_total_irradiance",
            "pvlib.location.Location.get_solarposition",
        ])

        return list(set(needs))  # Dedup

    def plan(self, contract: TaskContract, base_pv_spec: CanonicalPVSpec) -> ExecutionPlan:
        """
        Create execution plan from task contract.

        Args:
            contract: Task contract defining requirements
            base_pv_spec: Clarified PV spec (from ClarifierAgent)

        Returns:
            ExecutionPlan with subtasks
        """
        plan = ExecutionPlan(contract_id=contract.id)

        if contract.task_type == TaskType.SINGLE:
            # Single simulation, no reduction
            plan.add_subtask(Subtask(
                id=f"{contract.id}_sim_0",
                type="simulate",
                variant=None,
                pv_spec=base_pv_spec,
                description=f"Simulate {contract.name}",
                needs=self._resolve_dependencies(base_pv_spec)
            ))

        elif contract.task_type in [TaskType.COMPARISON, TaskType.SWEEP, TaskType.SENSITIVITY]:
            # Multiple variants + reduction
            if not contract.variants:
                raise ValueError(f"Task {contract.id} has type {contract.task_type} but no variants")

            simulate_subtask_ids = []

            # Create simulation subtask for each variant
            for i, variant in enumerate(contract.variants):
                # Clone base spec and apply variant parameters
                variant_spec = self._apply_variant_to_spec(base_pv_spec, variant, contract)

                subtask_id = f"{contract.id}_sim_{i}_{variant.name}"
                plan.add_subtask(Subtask(
                    id=subtask_id,
                    type="simulate",
                    variant=variant,
                    pv_spec=variant_spec,
                    description=f"Simulate {variant.name}: {variant.description or ''}",
                    needs=self._resolve_dependencies(variant_spec)
                ))
                simulate_subtask_ids.append(subtask_id)

            # Create reduction subtask
            plan.add_subtask(Subtask(
                id=f"{contract.id}_reduce",
                type="reduce",
                description=f"Reduce {len(contract.variants)} variants via {contract.reduction.operation}"
            ))
            plan.needs_reduction = True
            plan.reduction_depends_on = simulate_subtask_ids

        else:
            raise ValueError(f"Unknown task type: {contract.task_type}")

        self.logger.info(f"Created plan for {contract.id}: {len(plan.subtasks)} subtasks, "
                        f"reduction={plan.needs_reduction}")
        return plan

    def _apply_variant_to_spec(self, base_spec: CanonicalPVSpec, variant: Variant,
                               contract: TaskContract) -> CanonicalPVSpec:
        """
        Apply variant parameters to base PV spec.

        Creates a new spec with variant-specific overrides (e.g., tilt angle, tracking mode).
        """
        # Clone spec (create dict copy and reconstruct)
        spec_dict = base_spec.model_dump()

        # Apply variant parameters to appropriate spec fields
        for param, value in variant.parameters.items():
            applied = self._apply_parameter(spec_dict, param, value, variant.name)
            if not applied:
                self.logger.warning(f"Could not apply variant parameter {param}={value}")

        # Reconstruct spec from modified dict
        from agent.schemas.pv_spec_schema import CanonicalPVSpec
        return CanonicalPVSpec.model_validate(spec_dict)

    def _apply_parameter(self, spec_dict: Dict[str, Any], param: str, value: Any,
                        variant_name: str) -> bool:
        """
        Apply a single parameter to spec dictionary.

        Returns True if parameter was applied, False otherwise.
        """
        # Mapping of common parameter names to spec fields
        param_mappings = {
            # Orientation parameters
            "tilt": ("system", "tilt_deg"),
            "tilt_deg": ("system", "tilt_deg"),
            "azimuth": ("system", "azimuth_deg"),
            "azimuth_deg": ("system", "azimuth_deg"),
            "tracking": ("system", "tracker_mode"),
            "tracking_mode": ("system", "tracker_mode"),

            # System parameters
            "dc_capacity": ("system", "dc_capacity_w"),
            "dc_capacity_kw": ("system", "dc_capacity_w"),  # Will convert below
            "dc_capacity_w": ("system", "dc_capacity_w"),
            "losses": ("system", "losses_percent"),
            "losses_percent": ("system", "losses_percent"),

            # Temperature model
            "temperature_model": ("system", "temp_model"),
            "temp_model": ("system", "temp_model"),
        }

        # Handle kW to W conversion
        if param in ["dc_capacity_kw"] and value is not None:
            value = value * 1000

        if param in param_mappings:
            section, field = param_mappings[param]
            if section in spec_dict and isinstance(spec_dict[section], dict):
                spec_dict[section][field] = value
                self.logger.debug(f"Applied {variant_name}: {section}.{field} = {value}")
                return True

        # Try direct assignment to top-level sections
        for section in ["site", "met", "system", "output"]:
            if section in spec_dict and isinstance(spec_dict[section], dict):
                if param in spec_dict[section]:
                    spec_dict[section][param] = value
                    self.logger.debug(f"Applied {variant_name}: {section}.{param} = {value}")
                    return True

        return False

    def decompose_comparison(self, contract: TaskContract, base_spec: CanonicalPVSpec) -> List[CanonicalPVSpec]:
        """
        Convenience method: Decompose comparison into variant specs.

        Returns list of PV specs, one per variant.
        """
        if contract.task_type != TaskType.COMPARISON:
            raise ValueError(f"Task {contract.id} is not a COMPARISON")

        variant_specs = []
        for variant in contract.variants:
            spec = self._apply_variant_to_spec(base_spec, variant, contract)
            variant_specs.append(spec)

        return variant_specs

    def decompose_sweep(self, contract: TaskContract, base_spec: CanonicalPVSpec) -> List[CanonicalPVSpec]:
        """
        Convenience method: Decompose sweep into variant specs.

        Returns list of PV specs, one per sweep point.
        """
        if contract.task_type != TaskType.SWEEP:
            raise ValueError(f"Task {contract.id} is not a SWEEP")

        variant_specs = []
        for variant in contract.variants:
            spec = self._apply_variant_to_spec(base_spec, variant, contract)
            variant_specs.append(spec)

        return variant_specs
