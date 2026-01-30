"""
Plan-based execution engine for multi-step PV simulations.

This module implements a deterministic executor that follows a planner's decomposition.
"""

import json
from typing import Dict, List, Optional
from .planner_schema import validate_plan


class PlanExecutor:
    """
    Executes a plan by orchestrating SimAgent calls and deterministic comparisons.
    """

    def __init__(self, multi_agent):
        """
        Args:
            multi_agent: MultiAgentPV instance for calling agents
        """
        self.ma = multi_agent

    def execute_plan(self, plan: Dict, user_message: str, max_iterations: int = 3) -> Dict:
        """
        Execute a plan's subtasks in order.

        Args:
            plan: Plan dict from Planner agent
            user_message: Original user query
            max_iterations: Max retries per subtask

        Returns:
            Final result dict
        """
        # Validate plan
        valid, msg = validate_plan(plan)
        if not valid:
            return {
                "success": False,
                "final_text": f"Invalid plan: {msg}",
                "summary": {},
                "iterations": 0
            }

        task_type = plan['task_type']
        subtasks = plan['subtasks']
        base_assumptions = plan.get('base_assumptions', {})

        # Display plan
        self.ma.print("\n[cyan]=== EXECUTION PLAN ===[/cyan]")
        self.ma.print(f"Task Type: {task_type}")
        self.ma.print(f"Subtasks: {len(subtasks)}")
        for st in subtasks:
            action_desc = f"{st['id']}: {st['action']}"
            if st.get('variant'):
                action_desc += f" (variant: {st['variant']})"
            self.ma.print(f"  - {action_desc}")
        self.ma.print("[cyan]======================[/cyan]\n")

        # Execute subtasks
        subtask_results = []
        total_iterations = 0

        for subtask in subtasks:
            action = subtask['action']

            if action == "validate":
                # Validation-only task
                result = self._execute_validate(subtask, base_assumptions, user_message)
                subtask_results.append({"id": subtask['id'], "action": "validate", "result": result})

            elif action == "simulate":
                # Run simulation
                result = self._execute_simulate(
                    subtask, base_assumptions, user_message, max_iterations
                )
                subtask_results.append({
                    "id": subtask['id'],
                    "action": "simulate",
                    "output": result.get('output', {}),
                    "label": self._build_variant_label(subtask, base_assumptions)
                })
                total_iterations += result.get('iterations', 0)

                if not result.get('success'):
                    # Subtask failed, try recovery
                    recovery = plan.get('recovery_strategy', {})
                    if recovery.get('on_tool_error'):
                        self.ma.print(f"[yellow]Subtask {subtask['id']} failed, attempting recovery...[/yellow]")
                        # Could implement recovery ladder here
                    return result  # Early exit on failure

            elif action == "compare":
                # Deterministic comparison
                compare_on = subtask['compare_on']
                winner_rule = subtask['winner_rule']

                # Filter to simulate results only
                sim_results = [r for r in subtask_results if r['action'] == 'simulate']

                comparison = self._deterministic_compare(sim_results, compare_on, winner_rule)
                subtask_results.append({"id": subtask['id'], "action": "compare", "comparison": comparison})

            elif action == "explain":
                # Explanation without calculation
                return {
                    "success": True,
                    "final_text": f"Explanation: {user_message}",
                    "summary": {},
                    "iterations": 0
                }

        # Build final output based on task type
        final_schema = plan.get('final_schema', 'single_sim_v1')

        if task_type == "comparison":
            # Extract comparison from results
            comparison_result = next((r for r in subtask_results if r['action'] == 'compare'), None)

            if comparison_result:
                final_text = self._build_comparison_text(user_message, comparison_result['comparison'])
                return {
                    "success": True,
                    "final_text": final_text,
                    "summary": comparison_result['comparison'],
                    "iterations": total_iterations,
                    "plan": plan
                }

        elif task_type == "single_simulation":
            # Return first simulate result
            sim_result = next((r for r in subtask_results if r['action'] == 'simulate'), None)
            if sim_result:
                output = sim_result['output']
                final_text = self._build_single_sim_text(user_message, output)
                return {
                    "success": True,
                    "final_text": final_text,
                    "summary": output.get('results', output),
                    "iterations": total_iterations,
                    "plan": plan
                }

        # Default fallback
        return {
            "success": False,
            "final_text": "Plan execution completed but could not build final output",
            "summary": {},
            "iterations": total_iterations
        }

    def _execute_validate(self, subtask: Dict, base: Dict, user_message: str) -> Dict:
        """Execute validation-only subtask."""
        # For now, simple validation logic
        location = base.get('location', '')
        if 'invalid' in location.lower() or location == '':
            return {
                "valid": False,
                "error": "Invalid or missing location",
                "message": "Please provide a valid location"
            }
        return {"valid": True}

    def _execute_simulate(self, subtask: Dict, base: Dict, user_message: str, max_iterations: int) -> Dict:
        """Execute simulation subtask via SimAgent."""
        # Build context from base + variant
        context = {
            "user_query": user_message,
            "task_type": "simulation",
            "period": "365 days",
            "notes": [],
            "base_params": base,
            "variant": subtask.get('variant', {})
        }

        # Fetch initial API cards based on subtask needs
        initial_api_cards = []
        if subtask.get('needs'):
            initial_api_cards = self.ma.docs_agent.retrieve_cards_as_json(subtask['needs'])
            self.ma.print(f"[dim]Pre-loaded {len(initial_api_cards)} API cards for subtask {subtask['id']}[/dim]")

        # Call SimAgent with subtask context and API cards
        iteration = 0
        qa_feedback = None

        while iteration < max_iterations:
            iteration += 1

            sim_action = self.ma.call_simagent(context, feedback=qa_feedback, subtask=subtask, api_cards=initial_api_cards)

            if sim_action.get('action') != 'python':
                return {
                    "success": False,
                    "error": sim_action.get('error', 'Unknown'),
                    "iterations": iteration
                }

            code = sim_action.get('code', '')

            # Execute
            exec_result = self.ma.executor.execute_with_json_output(code, timeout=60)

            # QA validation
            qa_verdict = self.ma.call_qaagent(context, code, exec_result)

            if qa_verdict.get('verdict') == 'ok':
                return {
                    "success": True,
                    "output": exec_result.get('output', {}),
                    "iterations": iteration
                }
            elif qa_verdict.get('verdict') == 'fix':
                qa_feedback = qa_verdict.get('issues', [])
                continue
            else:
                return {
                    "success": False,
                    "error": "QA validation failed",
                    "iterations": iteration
                }

        return {
            "success": False,
            "error": "Max iterations reached",
            "iterations": iteration
        }

    def _deterministic_compare(self, results: List[Dict], compare_on: str, winner_rule: str) -> Dict:
        """Deterministic comparison of simulation results."""
        if len(results) < 2:
            return {"error": "Need at least 2 results to compare"}

        # Extract values
        comparisons = []
        for res in results:
            output = res.get('output', {})
            value = output.get(compare_on)
            if value is None:
                value = output.get('results', {}).get(compare_on)

            if value is not None:
                comparisons.append({
                    "id": res['id'],
                    "value": float(value),
                    "label": res.get('label', res['id'])
                })

        if len(comparisons) < 2:
            return {"error": f"Could not extract {compare_on} from results"}

        # Find winner
        if winner_rule == "max":
            winner = max(comparisons, key=lambda x: x['value'])
        else:  # min
            winner = min(comparisons, key=lambda x: x['value'])

        # Build comparison details
        comparison_details = []
        for comp in comparisons:
            comparison_details.append({
                "variant": comp['label'],
                compare_on: comp['value'],
                "is_winner": comp['id'] == winner['id']
            })

        return {
            "comparisons": comparison_details,
            "winner": {
                "variant": winner['label'],
                compare_on: winner['value']
            },
            "metric": compare_on
        }

    def _build_variant_label(self, subtask: Dict, base: Dict) -> str:
        """Build human-readable label for a variant."""
        variant = subtask.get('variant', {})
        if not variant:
            return "base"

        parts = []
        for key, val in variant.items():
            if key == "tilt":
                parts.append(f"tilt={val}°")
            elif key == "azimuth":
                parts.append(f"azimuth={val}°")
            elif key == "tracking":
                parts.append(f"{val} tracking")
            elif key == "temp_model":
                parts.append(f"temp_model={val}")
            elif key == "dc_ac_ratio":
                parts.append(f"DC/AC={val}")
            else:
                parts.append(f"{key}={val}")

        return ", ".join(parts)

    def _build_comparison_text(self, user_query: str, comparison: Dict) -> str:
        """Build final text for comparison result."""
        if "error" in comparison:
            return f"Comparison failed: {comparison['error']}"

        winner = comparison['winner']
        metric = comparison['metric']
        comparisons = comparison['comparisons']

        text = f"Comparison result:\n\n"
        for comp in comparisons:
            marker = "<- WINNER" if comp.get('is_winner') else ""
            text += f"- {comp['variant']}: {comp[metric]:.1f} {metric} {marker}\n"

        text += f"\nBest configuration: {winner['variant']} with {winner[metric]:.1f} {metric}"
        return text

    def _build_single_sim_text(self, user_query: str, output: Dict) -> str:
        """Build final text for single simulation."""
        results = output.get('results', output)

        text = "Simulation result:\n\n"
        for key, val in results.items():
            if isinstance(val, (int, float)):
                text += f"- {key}: {val:.2f}\n"
            else:
                text += f"- {key}: {val}\n"

        return text
