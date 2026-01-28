"""
Deterministic Reducer - Contract-compliant result combination.

This module provides deterministic (non-LLM) logic for reducing multiple
simulation variant results into final outputs for comparison/sweep tasks.
"""

from typing import Dict, List, Any, Optional
from agent.task_contract import TaskContract, ReductionSpec, TaskType
import logging


class DeterministicReducer:
    """
    Reduces multiple simulation variant results into final output.

    Handles comparisons, sweeps, and sensitivity analysis with deterministic
    logic (no LLM involved) to ensure consistent schema and calculations.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def reduce(self, contract: TaskContract, variant_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Reduce variant results according to contract reduction spec.

        Args:
            contract: Task contract defining reduction operation
            variant_results: List of simulation outputs, one per variant

        Returns:
            Combined output matching contract's expected_schema
        """
        if contract.task_type == TaskType.SINGLE:
            # No reduction needed for single simulations
            if len(variant_results) != 1:
                raise ValueError(f"SINGLE task expects 1 result, got {len(variant_results)}")
            return variant_results[0]

        if not contract.reduction:
            raise ValueError(f"Task {contract.id} requires reduction spec for type {contract.task_type}")

        reduction = contract.reduction

        if reduction.operation == "compare":
            return self._reduce_comparison(contract, variant_results, reduction)
        elif reduction.operation == "find_optimal":
            return self._reduce_sweep(contract, variant_results, reduction)
        elif reduction.operation == "compute_sensitivity":
            return self._reduce_sensitivity(contract, variant_results, reduction)
        else:
            raise ValueError(f"Unknown reduction operation: {reduction.operation}")

    def _reduce_comparison(self, contract: TaskContract, variant_results: List[Dict[str, Any]],
                          reduction: ReductionSpec) -> Dict[str, Any]:
        """
        Reduce comparison task (e.g., fixed vs tracker).

        Standard output schema for comparisons:
        - Individual variant outputs (e.g., fixed_kwh, tracker_kwh)
        - gain_percent: (variant_B - variant_A) / variant_A * 100
        - winner: name of variant with best metric
        """
        if len(variant_results) != len(contract.variants):
            raise ValueError(f"Expected {len(contract.variants)} results, got {len(variant_results)}")

        output = {}
        metric = reduction.comparison_metric
        if not metric:
            raise ValueError("Comparison requires comparison_metric")

        # Extract individual variant outputs
        variant_values = []
        for i, (variant, result) in enumerate(zip(contract.variants, variant_results)):
            variant_name = variant.name

            # Add variant-specific outputs to final result
            for field in reduction.output_fields:
                if field.startswith(variant_name + "_"):
                    # For comparison tasks, variant-specific fields typically come from the comparison metric
                    # E.g., "fixed_kwh" should get value from metric "daily_kwh"
                    # Try metric first, then fall back to field name parsing
                    if metric in result:
                        output[field] = result[metric]
                    else:
                        # Fallback: try direct field mapping
                        base_field = field[len(variant_name) + 1:]  # Remove "fixed_" prefix
                        if base_field in result:
                            output[field] = result[base_field]
                        else:
                            self.logger.warning(f"Field {base_field} not found in {variant_name} result")

            # Track metric value for gain calculation
            if metric in result:
                variant_values.append((variant_name, result[metric]))
            else:
                raise ValueError(f"Metric {metric} not found in {variant_name} result")

        # Compute gain_percent if formula provided
        if reduction.gain_formula and "gain_percent" in reduction.output_fields:
            output["gain_percent"] = self._compute_gain(
                variant_values, reduction.gain_formula, contract.variants
            )

        # Determine winner if rule provided
        if reduction.winner_rule and "winner" in reduction.output_fields:
            output["winner"] = self._determine_winner(variant_values, reduction.winner_rule)

        return output

    def _reduce_sweep(self, contract: TaskContract, variant_results: List[Dict[str, Any]],
                     reduction: ReductionSpec) -> Dict[str, Any]:
        """
        Reduce sweep task (e.g., tilt optimization).

        Standard output schema for sweeps:
        - optimal_<param>: parameter value that maximizes/minimizes metric
        - optimal_<metric>: metric value at optimal parameter
        - Boundary values (e.g., tilt_0_kwh, tilt_60_kwh)
        """
        if len(variant_results) != len(contract.variants):
            raise ValueError(f"Expected {len(contract.variants)} results, got {len(variant_results)}")

        metric = reduction.comparison_metric
        criterion = reduction.optimal_criterion
        if not metric or not criterion:
            raise ValueError("Sweep requires comparison_metric and optimal_criterion")

        output = {}

        # Find optimal variant
        optimal_idx = self._find_optimal_variant(variant_results, metric, criterion)
        optimal_variant = contract.variants[optimal_idx]
        optimal_result = variant_results[optimal_idx]

        # Extract sweep parameter (assume single parameter varies)
        sweep_param = self._identify_sweep_parameter(contract.variants)

        # Add optimal outputs
        # First, handle the sweep parameter optimal value
        # The output field might be "optimal_tilt" or "optimal_tilt_deg" when sweep_param is "tilt"
        optimal_param_field = None
        for field in reduction.output_fields:
            if field.startswith(f"optimal_{sweep_param}"):
                # This field is for the optimal parameter value
                output[field] = optimal_variant.parameters[sweep_param]
                optimal_param_field = field
                break

        # Handle optimal metric value - check for both full metric name and shorthand
        if f"optimal_{metric}" in reduction.output_fields:
            output[f"optimal_{metric}"] = optimal_result[metric]

        # Also check for shorthand like "optimal_kwh" when metric is "daily_kwh"
        for field in reduction.output_fields:
            if field.startswith("optimal_") and field != optimal_param_field and field != f"optimal_{metric}":
                # This is an optimal metric field (not the parameter, not already exact match)
                # It's likely a shorthand like "optimal_kwh" for metric "daily_kwh"
                if field not in output:  # Not already set
                    output[field] = optimal_result[metric]

        # Add boundary/specific point outputs
        for field in reduction.output_fields:
            if field.startswith(f"{sweep_param}_"):
                # Field like "tilt_0_kwh" or "tilt_60_kwh"
                try:
                    # Extract parameter value from field name
                    parts = field.split("_")
                    param_value_str = parts[1]  # e.g., "0" or "60"
                    param_value = float(param_value_str) if "." in param_value_str else int(param_value_str)

                    # Find variant with this parameter value
                    for variant, result in zip(contract.variants, variant_results):
                        if variant.parameters.get(sweep_param) == param_value:
                            # Extract metric from field suffix (e.g., "kwh" from "tilt_0_kwh")
                            metric_field = "_".join(parts[2:])  # e.g., "kwh"
                            # Try to find the field - first try the comparison metric, then the parsed field
                            if metric in result:
                                output[field] = result[metric]
                            elif metric_field in result:
                                output[field] = result[metric_field]
                            else:
                                self.logger.warning(f"Could not find metric for {field}")
                            break
                except (ValueError, IndexError) as e:
                    self.logger.warning(f"Could not parse sweep field {field}: {e}")

        return output

    def _reduce_sensitivity(self, contract: TaskContract, variant_results: List[Dict[str, Any]],
                           reduction: ReductionSpec) -> Dict[str, Any]:
        """
        Reduce sensitivity analysis task.

        Output schema depends on analysis type, typically:
        - delta_<metric>: change in metric across variants
        - percent_change: percentage sensitivity
        """
        # Similar to comparison but may include multiple deltas
        # For now, use comparison logic
        return self._reduce_comparison(contract, variant_results, reduction)

    def _compute_gain(self, variant_values: List[tuple], formula: str, variants: List) -> float:
        """
        Compute gain percentage using formula.

        Formula format: "(tracker - fixed) / fixed * 100"
        """
        # Build namespace with variant values
        namespace = {}
        for variant_name, value in variant_values:
            namespace[variant_name] = value

        try:
            # Evaluate formula safely
            result = eval(formula, {"__builtins__": {}}, namespace)
            return float(result)
        except Exception as e:
            self.logger.error(f"Failed to compute gain with formula '{formula}': {e}")
            # Fallback: simple percent difference between first two variants
            if len(variant_values) >= 2:
                baseline = variant_values[0][1]
                comparison = variant_values[1][1]
                return (comparison - baseline) / baseline * 100
            return 0.0

    def _determine_winner(self, variant_values: List[tuple], rule: str) -> str:
        """
        Determine winner using rule.

        Rule format: "max(daily_kwh)" or "min(cost)"
        """
        if rule.startswith("max("):
            # Find variant with maximum value
            winner = max(variant_values, key=lambda x: x[1])
            return winner[0]
        elif rule.startswith("min("):
            # Find variant with minimum value
            winner = min(variant_values, key=lambda x: x[1])
            return winner[0]
        else:
            self.logger.warning(f"Unknown winner rule: {rule}, returning first variant")
            return variant_values[0][0] if variant_values else "unknown"

    def _find_optimal_variant(self, variant_results: List[Dict[str, Any]],
                             metric: str, criterion: str) -> int:
        """Find index of optimal variant based on criterion."""
        metric_values = []
        for result in variant_results:
            if metric not in result:
                raise ValueError(f"Metric {metric} not found in result")
            metric_values.append(result[metric])

        if criterion == "maximize":
            return metric_values.index(max(metric_values))
        elif criterion == "minimize":
            return metric_values.index(min(metric_values))
        else:
            raise ValueError(f"Unknown optimal criterion: {criterion}")

    def _identify_sweep_parameter(self, variants: List) -> str:
        """
        Identify which parameter is being swept.

        Assumes exactly one parameter varies across variants.
        """
        if not variants:
            raise ValueError("No variants provided")

        # Get all parameter names
        all_params = set()
        for variant in variants:
            all_params.update(variant.parameters.keys())

        # Find parameter that varies
        varying_params = []
        for param in all_params:
            values = [v.parameters.get(param) for v in variants if param in v.parameters]
            if len(set(values)) > 1:  # Parameter varies
                varying_params.append(param)

        if len(varying_params) == 0:
            raise ValueError("No varying parameters found in sweep")
        if len(varying_params) > 1:
            self.logger.warning(f"Multiple varying parameters: {varying_params}, using first")

        return varying_params[0]


def validate_reduction_output(contract: TaskContract, reduced_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate reduced output against contract.

    This is a convenience wrapper around contract.validate_output().
    """
    return contract.validate_output(reduced_output)
