#!/usr/bin/env python3
"""
Helio — AI Companion for Solar PV Simulation

Multi-agent CLI with Router -> SimAgent -> QAAgent architecture.
Provides better reliability through separation of concerns and validation.
"""

import sys
import os
import json
import re
import uuid
import time
import random
from pathlib import Path
from typing import List, Dict, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .openrouter_client import OpenRouterClient
from .executor import PythonExecutor
from .multi_agent_prompts import ROUTER_PROMPT, SIMAGENT_PROMPT, QAAGENT_PROMPT
from .prompts import SMALL_TALK_PATTERNS
from .planner_schema import PLANNER_PROMPT, validate_plan
from .structured_logger import StructuredLogger
from . import auth
from pydantic import TypeAdapter, ValidationError
from .handoff_schemas import RouterOutput, AgentAction, QAVerdict, NeedAPIAction
from .docs_agent import DocsAgent
from .tools.compliance import check_api_compliance
from .error_diagnosis import ErrorDiagnosisAgent


class MultiAgentPV:
    """
    Helio - Multi-agent PV simulation companion.

    Flow:
    1. Router classifies query and determines task
    2. SimAgent generates Python code
    3. Code executes in sandbox
    4. QAAgent validates result and provides feedback
    5. Loop until QA approves or max iterations
    """

    # ASCII banner (Windows-friendly, no Unicode)
    HELIO_BANNER = r"""
 _   _      _ _
| | | | ___| (_) ___
| |_| |/ _ \ | |/ _ \
|  _  |  __/ | | (_) |
|_| |_|\___|_|_|\___/

PV Simulation Companion
"""

    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4.5",
        venv_path: Optional[str] = None,
        log_episodes: bool = False,
        episode_dir: Optional[str] = None,
        use_planner: bool = False,
        debug: bool = False,
        trace_file: Optional[Path] = None,
        temperature: float = 0.0,
        seed: Optional[int] = None,
        use_openrouter: bool = False,
        use_clarifier: bool = False
    ):
        # Initialize console first (needed for print statements)
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None

        # Initialize OpenRouter client
        # Ensure API key is available
        if not os.environ.get("OPENROUTER_API_KEY"):
            key = auth.get_api_key()
            if key:
                os.environ["OPENROUTER_API_KEY"] = key
            elif not debug and not os.environ.get("PYTEST_CURRENT_TEST"): # context check if feasible, or just warn
                self.print("[yellow]Warning: OpenRouter API key not found. Check auth.[/yellow]")

        self.client = OpenRouterClient(model=model)
        self.print(f"[cyan]Using OpenRouter with model: {model}[/cyan]")
        self.model = model
        self.log_episodes = log_episodes
        self.episode_dir = Path(episode_dir) if episode_dir else Path("runs/episodes")
        self.use_planner = use_planner
        self.use_clarifier = use_clarifier
        self.debug = debug
        self.temperature = temperature

        # Set random seed (use time-based if not specified)
        self.seed = seed if seed is not None else int(time.time() * 1000) % (2**31)
        random.seed(self.seed)

        # Set numpy seed if available
        try:
            import numpy as np
            np.random.seed(self.seed)
        except ImportError:
            pass

        # Initialize structured logger
        self.session_id = str(uuid.uuid4())[:8]
        self.logger = StructuredLogger(
            session_id=self.session_id,
            log_file=trace_file,
            debug=debug
        )

        # Log seed initialization
        seed_source = "user_specified" if seed is not None else "time_based"
        self.logger.log_event(
            agent="System",
            event_type="initialization",
            step_name="seed_set",
            data={
                "random_seed": self.seed,
                "seed_source": seed_source,
                "temperature": self.temperature,
                "use_clarifier": self.use_clarifier
            }
        )

        # Pass logger to executor (use secure executor with fallback)
        try:
            from .secure_executor import SecureExecutor
            self.executor = SecureExecutor(venv_path=venv_path, logger=self.logger)
            if self.executor.sandbox_available:
                self.print("[green]OK Secure sandbox active[/green]")
            else:
                self.print("[yellow]WARNING Sandbox not available, using basic isolation[/yellow]")
        except ImportError:
            # Fallback to basic executor if secure_executor not available
            from .executor import PythonExecutor
            self.executor = PythonExecutor(venv_path=venv_path, logger=self.logger)
            self.print("[yellow]WARNING Using basic executor (run install_security.sh for enhanced security)[/yellow]")

        # Initialize clarifier if enabled
        if self.use_clarifier:
            from .clarifier import ClarifierAgent
            self.clarifier = ClarifierAgent(llm_client=self.client, logger=self.logger)

        # Initialize plan executor if enabled
        if self.use_planner:
            from .plan_executor import PlanExecutor
            self.plan_executor = PlanExecutor(self)

        # Initialize DocsAgent (The Librarian)
        self.docs_agent = DocsAgent()

        # Initialize Diagnoser (The Fixer)
        self.diagnoser = ErrorDiagnosisAgent(llm_client=self.client)

        if self.log_episodes:
            self.episode_dir.mkdir(parents=True, exist_ok=True)

        if debug:
            self.print(f"[yellow]DEBUG MODE ENABLED (session: {self.session_id}, seed: {self.seed}, temp: {self.temperature})[/yellow]")

    def print(self, text: str, style: str = ""):
        """Print with rich formatting if available."""
        if self.console:
            self.console.print(text, style=style)
        else:
            print(text)

    def print_panel(self, content, title: str = "", style: str = ""):
        """Print panel with rich if available."""
        if self.console:
            self.console.print(Panel(content, title=title, style=style))
        else:
            print(f"\n=== {title} ===\n{content}\n")

    def is_small_talk(self, message: str) -> bool:
        """Check if message is casual small talk."""
        message_lower = message.lower().strip()
        for pattern in SMALL_TALK_PATTERNS:
            if re.search(pattern, message_lower):
                return True
        return False

    def extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from model response."""
        text = text.strip()

        # Try direct parse
        if text.startswith('{'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try first { to last }
        if '{' in text and '}' in text:
            first_brace = text.find('{')
            last_brace = text.rfind('}')
            if first_brace < last_brace:
                try:
                    return json.loads(text[first_brace:last_brace+1])
                except json.JSONDecodeError:
                    pass

        # Try code block
        matches = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError:
                pass

        return None

    def deterministic_compare(self, results: List[Dict], compare_on: str, winner_rule: str) -> Dict:
        """
        Deterministic comparison of simulation results.

        Args:
            results: List of simulation outputs with 'id' and data
            compare_on: Field to compare (e.g., 'annual_kwh')
            winner_rule: 'max' or 'min'

        Returns:
            Comparison summary with winner
        """
        if len(results) < 2:
            return {"error": "Need at least 2 results to compare"}

        # Extract values
        comparisons = []
        for res in results:
            value = res.get('output', {}).get(compare_on)
            if value is None:
                value = res.get('output', {}).get('results', {}).get(compare_on)

            if value is not None:
                comparisons.append({
                    "id": res['id'],
                    "value": value,
                    "label": res.get('label', res['id'])
                })

        if len(comparisons) < 2:
            return {"error": f"Could not extract {compare_on} from results"}

        # Find winner
        if winner_rule == "max":
            winner = max(comparisons, key=lambda x: x['value'])
        else:  # min
            winner = min(comparisons, key=lambda x: x['value'])

        # Calculate differences
        comparison_details = []
        for comp in comparisons:
            diff = comp['value'] - winner['value'] if winner_rule == "min" else winner['value'] - comp['value']
            pct_diff = (diff / winner['value'] * 100) if winner['value'] != 0 else 0

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

    def call_router(self, user_query: str) -> Dict:
        """Route the user query to determine task type."""
        self.print("[cyan]-> Router: Analyzing query...[/cyan]")

        messages = [
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_query}
        ]

        # Build options for deterministic execution
        options = {}
        if self.temperature == 0.0:
            options["top_k"] = 1  # Greedy decoding when temperature is 0
        if self.seed is not None:
            options["seed"] = self.seed

        response = self.client.chat(messages, temperature=self.temperature, format="json", **options)

        if "error" in response:
            return {"route": "unknown", "error": response["error"]}

        routing = self.extract_json(response["message"]["content"])

        if routing:
            try:
                # Validate with Pydantic
                validated_route = RouterOutput.model_validate(routing)
                routing = validated_route.model_dump()
                
                self.print(f"  Route: {routing['route']}, Task: {routing.get('task_type', 'N/A')}, Period: {routing.get('period', 'N/A')}")
                if routing.get('reasoning'):
                    self.print(f"  [dim]Reasoning: {routing['reasoning']}[/dim]")

                # Log decision
                self.logger.log_decision(
                    agent="Router",
                    decision=f"route={routing['route']}, task={routing.get('task_type')}",
                    reasoning=routing.get('reasoning', 'No reasoning provided'),
                    step_name="routing",
                    metadata={"route": routing['route'], "task_type": routing.get('task_type'), "period": routing.get('period')}
                )

                return routing
            except ValidationError as e:
                self.print(f"[red]Router schema validation failed: {str(e)}[/red]")
                return {"route": "unknown", "error": f"Schema validation failed: {str(e)}"}
        else:
            return {"route": "unknown", "error": "Could not parse routing decision"}

    def call_planner(self, user_message: str) -> Dict:
        """Decompose user request into subtasks."""
        self.print("[cyan]-> Planner: Decomposing task...[/cyan]")

        prompt = PLANNER_PROMPT.format(user_prompt=user_message)
        messages = [{"role": "user", "content": prompt}]

        # Build options for deterministic execution
        options = {}
        if self.temperature == 0.0:
            options["top_k"] = 1
        if self.seed is not None:
            options["seed"] = self.seed

        response = self.client.chat(messages, temperature=self.temperature, format="json", **options)

        if "error" in response:
            return {"error": response["error"]}

        plan = self.extract_json(response["message"]["content"])

        if not plan:
            return {"error": "Planner did not return valid JSON"}

        # Validate plan
        valid, msg = validate_plan(plan)
        if not valid:
            return {"error": f"Invalid plan: {msg}"}

        # Log reasoning if present
        if plan.get('reasoning'):
            self.print(f"  [dim]Reasoning: {plan['reasoning']}[/dim]")

        # Log planner decision
        self.logger.log_decision(
            agent="Planner",
            decision=f"task_type={plan.get('task_type')}, subtasks={len(plan.get('subtasks', []))}",
            reasoning=plan.get('reasoning', 'No reasoning provided'),
            step_name="task_decomposition",
            metadata={
                "task_type": plan.get('task_type'),
                "num_subtasks": len(plan.get('subtasks', [])),
                "final_schema": plan.get('final_schema')
            }
        )

        return plan

    def call_simagent(self, context: Dict, feedback: Optional[List[Dict]] = None, 
                     subtask: Optional[Dict] = None, api_cards: Optional[List[Dict]] = None) -> Dict:
        """
        Generate simulation code.
        Handles API retrieval loop and compliance checking.
        """
        self.print("[cyan]-> SimAgent: Generating code...[/cyan]")
        
        # Initialize api_cards if not provided or empty
        current_api_cards = api_cards or []
        
        # Loop for potential retries (need_api or compliance failure)
        # We limit specific retries to avoid infinite loops, separate from outer loop
        internal_retries = 3
        current_feedback = feedback

        for i in range(internal_retries):
            messages = [{"role": "system", "content": SIMAGENT_PROMPT}]

            # Build context message
            context_msg = f"Task: {context['task_type']}\n"
            context_msg += f"Period: {context['period']}\n"
            context_msg += f"Query: {context['user_query']}\n"

            if context.get('notes'):
                context_msg += f"Notes: {', '.join(context['notes'])}\n"

            # Add subtask constraints if provided
            if subtask:
                context_msg += f"\nSUBTASK: {subtask['id']}\n"
                context_msg += f"ACTION: {subtask['action']}\n"
                if 'variant' in subtask:
                    context_msg += f"VARIANT PARAMETERS: {json.dumps(subtask['variant'])}\n"
                if 'must_return' in subtask:
                    context_msg += f"MUST RETURN: {', '.join(subtask['must_return'])}\n"

            # Add API Cards (Critical for enforcement)
            if current_api_cards:
                cards_json = json.dumps(current_api_cards, indent=2)
                context_msg += f"\nALLOWED APIS (You MUST use these or request new ones):\n{cards_json}\n"
                # Add guidance on importing
                context_msg += "\nImport Guide:\n"
                for card in current_api_cards:
                    if isinstance(card, dict) and 'import_stmt' in card:
                        context_msg += f"- {card['import_stmt']}\n"

            messages.append({"role": "user", "content": context_msg})

            # Add QA feedback or Compliance feedback if retrying
            if current_feedback:
                feedback_msg = "VALIDATION FAILED. Fix these issues:\n\n"
                for issue in current_feedback:
                    feedback_msg += f"- {issue.get('description', 'Unknown issue')}\n"
                    if issue.get('fix_suggestion'):
                         feedback_msg += f"  FIX: {issue['fix_suggestion']}\n\n"
                
                messages.append({"role": "user", "content": feedback_msg})

            # Build options for deterministic execution
            options = {}
            if self.temperature == 0.0:
                options["top_k"] = 1
            if self.seed is not None:
                options["seed"] = self.seed

            response = self.client.chat(messages, temperature=self.temperature, **options)

            if "error" in response:
                return {"action": "error", "error": response["error"]}

            action_json = self.extract_json(response["message"]["content"])
            
            if not action_json:
                 return {"action": "error", "error": "SimAgent did not return valid JSON"}

            try:
                # Validate with Pydantic Union
                adapter = TypeAdapter(AgentAction)
                action_obj = adapter.validate_python(action_json)
                
                # Check action type
                if action_obj.action == "need_api":
                    self.print(f"[yellow]SimAgent requested APIs: {action_obj.symbols}[/yellow]")
                    # Retrieve new cards
                    new_cards = self.docs_agent.retrieve_cards_as_json(action_obj.symbols)
                    if new_cards:
                        # Append non-duplicate cards
                        existing_symbols = {c['symbol'] for c in current_api_cards}
                        added_count = 0
                        for card in new_cards:
                            if card['symbol'] not in existing_symbols:
                                current_api_cards.append(card)
                                added_count += 1
                        
                        self.print(f"[green]Retrieved {added_count} new API cards[/green]")
                        current_feedback = [{"description": f"Retrieved {added_count} new APIs. Please retry using them.", "type": "info"}]
                        continue # Retry loop
                    else:
                        return {"action": "error", "error": f"Could not find APIs: {action_obj.symbols}"}

                elif action_obj.action == "python":
                     # Check Compliance
                     from agent.schemas.api_cards import APICard
                     # Convert dicts back to APICard objects for the checker
                     card_objs = []
                     for c in current_api_cards:
                         try:
                             card_objs.append(APICard(**c))
                         except ValidationError:
                             pass # Skip invalid
                     
                     compliance = check_api_compliance(action_obj.code, card_objs)

                     if not compliance.allowed:
                         self.print(f"[red]Compliance Check Failed: {compliance.violations}[/red]")

                         # If syntax error, show the problematic code for debugging
                         if any("Syntax Error" in v for v in compliance.violations):
                             self.print("[yellow]Generated code with syntax error:[/yellow]")
                             if self.console:
                                 self.console.print(Syntax(action_obj.code, "python", theme="monokai", line_numbers=True))
                             else:
                                 print(action_obj.code)

                         # Try to automatically fix by treating violations as missing APIs?
                         # Extract symbols from violations? 
                         # Violations are like "Forbidden usage: pvlib.foo.bar"
                         
                         missing_symbols = []
                         for v in compliance.violations:
                             if "Forbidden usage: " in v:
                                 sym = v.replace("Forbidden usage: ", "").strip()
                                 missing_symbols.append(sym)
                         
                         if missing_symbols:
                             self.print(f"[yellow]Auto-retrieving missing symbols: {missing_symbols}[/yellow]")
                             new_cards = self.docs_agent.retrieve_cards_as_json(missing_symbols)
                             # Add to allowlist and retry
                             existing_symbols = {c['symbol'] for c in current_api_cards}
                             count = 0
                             for card in new_cards:
                                 if card['symbol'] not in existing_symbols:
                                     current_api_cards.append(card)
                                     count += 1
                             
                             if count > 0:
                                 current_feedback = [{"description": f"Compliance failed. Added {count} missing APIs. Please retry.", "fix_suggestion": "Use the newly provided APIs"}]
                                 continue
                             else:
                                 # We couldn't find them, so genuinely forbidden
                                 return {"action": "error", "error": f"Compliance violations (could not auto-resolve): {compliance.violations}"}
                         else:
                             return {"action": "error", "error": f"Compliance violations: {compliance.violations}"}
                     
                     # If compliant, return the python action
                     # Use repaired code if syntax was auto-fixed
                     if compliance.repaired_code is not None:
                         self.print("[yellow]Compliance: syntax auto-repaired[/yellow]")
                         result = action_obj.model_dump()
                         result['code'] = compliance.repaired_code
                         self.print("[green]Compliance Check Passed[/green]")
                         return result
                     self.print("[green]Compliance Check Passed[/green]")
                     return action_obj.model_dump()

                else:
                    return action_obj.model_dump()

            except ValidationError as e:
                return {"action": "error", "error": f"Schema validation failed: {str(e)}"}
        
        return {"action": "error", "error": "SimAgent Loop Exhausted (Needs API)"}

    def call_qaagent(self, context: Dict, code: str, exec_result: Dict) -> Dict:
        """Validate code and results."""
        self.print("[cyan]-> QAAgent: Validating result...[/cyan]")

        messages = [{"role": "system", "content": QAAGENT_PROMPT}]

        # Build validation context
        qa_context = f"USER QUERY: {context['user_query']}\n\n"
        qa_context += f"TASK TYPE: {context['task_type']}\n"
        qa_context += f"EXPECTED PERIOD: {context['period']}\n\n"
        qa_context += f"GENERATED CODE:\n```python\n{code}\n```\n\n"

        if exec_result['success']:
            qa_context += f"EXECUTION: SUCCESS\n\n"
            qa_context += f"OUTPUT:\n{json.dumps(exec_result.get('output', {}), indent=2)}\n"
        else:
            qa_context += f"EXECUTION: FAILED\n\n"
            qa_context += f"ERROR:\n{exec_result.get('error', 'Unknown error')}\n"

            if exec_result.get('stderr'):
                qa_context += f"\nSTDERR:\n{exec_result['stderr']}\n"

        messages.append({"role": "user", "content": qa_context})

        # Build options for deterministic execution
        options = {}
        if self.temperature == 0.0:
            options["top_k"] = 1
        if self.seed is not None:
            options["seed"] = self.seed

        response = self.client.chat(messages, temperature=self.temperature, format="json", **options)

        if "error" in response:
            return {"verdict": "error", "error": response["error"]}

        verdict_json = self.extract_json(response["message"]["content"])

        if verdict_json:
            try:
                # Validate with Pydantic
                validated_verdict = QAVerdict.model_validate(verdict_json)
                verdict = validated_verdict.model_dump()

                # Print verdict
                if verdict['verdict'] == 'ok':
                    self.print("  [green]OK QA Verdict: OK - proceed to finalize[/green]")
                    if verdict.get('reasoning'):
                        self.print(f"  [dim]{verdict['reasoning']}[/dim]")
                else:
                    self.print(f"  [yellow]! QA Verdict: FIX - {len(verdict.get('issues', []))} issues found[/yellow]")
                    if verdict.get('reasoning'):
                        self.print(f"  [dim]{verdict['reasoning']}[/dim]")
                    for issue in verdict.get('issues', []):
                        self.print(f"    - {issue['description']}", style="yellow")

                # Log decision
                self.logger.log_decision(
                    agent="QAAgent",
                    decision=f"verdict={verdict['verdict']}",
                    reasoning=verdict.get('reasoning', 'No reasoning provided'),
                    step_name="qa_validation",
                    metadata={
                        "verdict": verdict['verdict'],
                        "num_issues": len(verdict.get('issues', [])),
                        "issue_types": [issue.get('type') for issue in verdict.get('issues', [])]
                    }
                )

                return verdict
            except ValidationError as e:
                self.print(f"[red]QA schema validation failed: {str(e)}[/red]")
                return {"verdict": "error", "error": f"Schema validation failed: {str(e)}"}
        else:
            self.print(f"[red]Failed to parse QA verdict. Raw response:[/red]\n{response['message']['content']}")
            return {"verdict": "error", "error": "Could not parse QA verdict"}

    def run_with_clarification(self, user_message: str, max_iterations: int = 5) -> Dict:
        """
        Multi-agent loop with clarification step (Phase 1 self-correction).

        Flow:
        1. Clarifier: Convert user prompt -> canonical PV spec JSON
        2. Validate spec completeness
        3. SimAgent: Generate code from spec
        4. Execute and validate
        5. Return results

        Returns:
            {"success": bool, "final_text": str, "summary": dict, "iterations": int, "spec": dict}
        """
        if not self.use_clarifier:
            raise ValueError("Clarifier not enabled. Set use_clarifier=True in constructor.")

        # Check for small talk
        if self.is_small_talk(user_message):
            return {
                "success": True,
                "final_text": "You're welcome! Let me know if you need any PV simulations.",
                "summary": {},
                "iterations": 0,
                "local_ack": True
            }

        # Step 1: Clarify user prompt -> canonical PV spec
        self.print("\n[bold cyan]Clarifying simulation requirements...[/bold cyan]")

        try:
            pv_spec, clarification_summary = self.clarifier.clarify(user_message)
        except ValueError as e:
            return {
                "success": False,
                "final_text": f"Clarification failed: {str(e)}",
                "summary": {},
                "iterations": 0,
                "error": str(e)
            }

        # Show clarification to user
        self.print(f"\n[green]Simulation Plan:[/green] {clarification_summary}")
        if pv_spec.assumptions:
            self.print(f"[dim]   Assumptions: {', '.join(pv_spec.assumptions[:3])}{'...' if len(pv_spec.assumptions) > 3 else ''}[/dim]")

        # Save spec artifact
        spec_file = Path(f"artifacts/spec_{self.session_id}.json")
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(pv_spec.model_dump_json(indent=2))
        self.print(f"[dim]   Spec saved: {spec_file}[/dim]")

        # Step 2: Generate code from canonical spec
        # Build enhanced context with spec
        context = {
            "user_query": user_message,
            "task_type": pv_spec.output.task_type.value,
            "pv_spec": pv_spec.model_dump(),
            "clarification": clarification_summary
        }

        iteration = 0
        qa_feedback = None
        tool_outputs = []

        # Pre-seed session API cards with core pvlib signatures
        try:
            session_api_cards = self.docs_agent.get_core_cards()
        except Exception:
            session_api_cards = []

        while iteration < max_iterations:
            iteration += 1
            self.logger.log_iteration(iteration, "started", metadata={"max_iterations": max_iterations})

            # Generate code (SimAgent uses spec if available)
            sim_action = self.call_simagent(context, feedback=qa_feedback, api_cards=session_api_cards)

            if sim_action.get('action') != 'python':
                return {
                    "success": False,
                    "final_text": f"SimAgent error: {sim_action.get('error', 'Unknown')}",
                    "summary": {},
                    "iterations": iteration,
                    "spec": pv_spec.model_dump()
                }

            code = sim_action.get('code', '')

            # Display code
            if self.console:
                self.console.print("\n[cyan]-> Executing Python code:[/cyan]")
                self.console.print(Syntax(code, "python", theme="monokai", line_numbers=True))
            else:
                print("\n-> Executing Python code:")
                print(code)

            # Execute code
            exec_result = self.executor.execute_with_json_output(code, timeout=60)
            tool_outputs.append({"code": code, "result": exec_result})

            # Display execution result
            if exec_result["success"]:
                self.print("\n[green]OK Execution successful[/green]")
            else:
                self.print("\n[red]X Execution failed[/red]")
                self.print(f"Error: {exec_result.get('error', 'Unknown')[:200]}...", style="red")

            # Validate output against spec schema
            if exec_result["success"]:
                schema_valid = self._validate_output_schema(exec_result.get("output", {}), pv_spec.output.schema)
                if not schema_valid:
                    exec_result["success"] = False
                    exec_result["error"] = f"Output schema mismatch. Expected: {pv_spec.output.schema}"
                    self.print(f"[yellow]WARNING Output doesn't match expected schema[/yellow]")

            # QA validation
            qa_verdict = self.call_qaagent(context, code, exec_result)

            if qa_verdict.get('verdict') == 'ok':
                # Success!
                output = exec_result.get('output', {})
                return {
                    "success": True,
                    "final_text": f"Simulation complete: {clarification_summary}",
                    "summary": output,
                    "iterations": iteration,
                    "spec": pv_spec.model_dump()
                }

            elif qa_verdict.get('verdict') == 'fail':
                # Continue loop with QA feedback
                qa_feedback = qa_verdict.get('feedback', 'Try again')
                self.print(f"[yellow]-> QA rejected, iteration {iteration}/{max_iterations}[/yellow]")
                if qa_verdict.get('reasoning'):
                    self.print(f"   Reason: {qa_verdict['reasoning'][:150]}...", style="dim")
                continue

            else:
                # QA error
                return {
                    "success": False,
                    "final_text": f"QA error: {qa_verdict.get('error', 'Unknown')}",
                    "summary": {},
                    "iterations": iteration,
                    "spec": pv_spec.model_dump()
                }

        # Max iterations reached
        return {
            "success": False,
            "final_text": f"Max iterations ({max_iterations}) reached without success",
            "summary": {},
            "iterations": iteration,
            "spec": pv_spec.model_dump()
        }

    def _validate_output_schema(self, output: dict, expected_schema: dict) -> bool:
        """Validate output matches expected schema (simple field presence check)."""
        for field in expected_schema.keys():
            if field not in output:
                return False
        return True

    def run_tool_loop(self, user_message: str, max_iterations: int = 5) -> Dict:
        """
        Multi-agent tool loop.

        Returns:
            {"success": bool, "final_text": str, "summary": dict, "iterations": int}
        """
        # If clarifier is enabled, use clarification path
        if self.use_clarifier:
            return self.run_with_clarification(user_message, max_iterations)

        # Check for small talk first
        if self.is_small_talk(user_message):
            return {
                "success": True,
                "final_text": "You're welcome! Let me know if you need any PV simulations.",
                "summary": {},
                "iterations": 0,
                "local_ack": True
            }

        # Step 1: Route the query
        routing = self.call_router(user_message)

        if routing.get('route') == 'ack':
            return {
                "success": True,
                "final_text": "I can help with PV simulations. Try asking about energy calculations or comparisons.",
                "summary": {},
                "iterations": 0,
                "routed_ack": True
            }

        if routing.get('route') != 'simulate' or not routing.get('needs_python'):
            return {
                "success": False,
                "final_text": f"Could not route query: {routing.get('error', 'Unknown routing error')}",
                "summary": {},
                "iterations": 0
            }

        # PLANNER PATH: Use plan-based execution if enabled
        if self.use_planner:
            plan = self.call_planner(user_message)

            if "error" in plan:
                # Fallback to regular execution
                self.print(f"[yellow]Planner failed: {plan['error']}, using regular execution[/yellow]")
            else:
                return self.plan_executor.execute_plan(plan, user_message, max_iterations=max_iterations)

        # REGULAR PATH: Original multi-agent flow
        # Build context for agents
        context = {
            "user_query": user_message,
            "task_type": routing.get('task_type', 'unknown'),
            "period": routing.get('period', '365 days'),
            "notes": routing.get('notes', [])
        }

        iteration = 0
        qa_feedback = None
        tool_outputs = []

        # Pre-seed session API cards with core pvlib signatures
        # This prevents API mismatch drift (e.g., wrong kwarg names)
        try:
            session_api_cards = self.docs_agent.get_core_cards()
            if session_api_cards:
                self.print(f"[dim]Pre-loaded {len(session_api_cards)} core API cards[/dim]")
        except Exception:
            session_api_cards = []

        while iteration < max_iterations:
            iteration += 1
            self.logger.log_iteration(iteration, "started", metadata={"max_iterations": max_iterations})

            # Step 2: Generate code
            sim_action = self.call_simagent(context, feedback=qa_feedback, api_cards=session_api_cards)

            if sim_action.get('action') != 'python':
                return {
                    "success": False,
                    "final_text": f"SimAgent error: {sim_action.get('error', 'Unknown')}",
                    "summary": {},
                    "iterations": iteration
                }

            code = sim_action.get('code', '')

            # Display code
            if self.console:
                self.console.print("\n[cyan]-> Executing Python code:[/cyan]")
                self.console.print(Syntax(code, "python", theme="monokai", line_numbers=True))
            else:
                print("\n-> Executing Python code:")
                print(code)

            # Step 3: Execute code
            exec_result = self.executor.execute_with_json_output(code, timeout=60)
            tool_outputs.append({"code": code, "result": exec_result})

            # Display execution result
            if exec_result["success"]:
                self.print("\n[green]OK Execution successful[/green]")
            else:
                self.print("\n[red]X Execution failed[/red]")
                self.print(f"Error: {exec_result.get('error', 'Unknown')[:200]}...", style="red")
                
                # FixAgent: Diagnose and Retrieve
                error_context = self.executor.extract_error_context(exec_result)
                diagnosis = self.diagnoser.diagnose(code, error_context)
                
                if diagnosis.get('missing_symbols'):
                    missing = diagnosis['missing_symbols']
                    self.print(f"[yellow]FixAgent detected missing symbols: {missing}[/yellow]")
                    new_cards = self.docs_agent.retrieve_cards_as_json(missing)
                    # Add to session cards (need to define session_api_cards outside loop)
                    # Note: We assume session_api_cards is defined in the outer scope, which we'll add next
                    if 'session_api_cards' in locals():
                         for card in new_cards:
                             session_api_cards.append(card)
                         self.print(f"[green]Added {len(new_cards)} cards for repair.[/green]")

            # Step 4: QA validation
            qa_verdict = self.call_qaagent(context, code, exec_result)

            if qa_verdict.get('verdict') == 'ok':
                # Success! Generate final response
                output = exec_result.get('output', {})

                if isinstance(output, dict):
                    summary = output.get('results', output)

                    # Build final text
                    final_text = self._build_final_text(context, output)

                    final_result = {
                        "success": True,
                        "final_text": final_text,
                        "summary": summary,
                        "iterations": iteration,
                        "tool_outputs": tool_outputs
                    }

                    self.logger.save_session_summary(final_result)
                    return final_result
                else:
                    return {
                        "success": True,
                        "final_text": str(output),
                        "summary": {},
                        "iterations": iteration,
                        "tool_outputs": tool_outputs
                    }

            elif qa_verdict.get('verdict') == 'fix':
                # Need to retry with QA feedback
                qa_feedback = qa_verdict.get('issues', [])
                self.print(f"\n[yellow]! Retrying with QA feedback (iteration {iteration}/{max_iterations})[/yellow]")
                continue

            else:
                return {
                    "success": False,
                    "final_text": f"QA error: {qa_verdict.get('error', 'Unknown')}",
                    "summary": {},
                    "iterations": iteration
                }

        # Max iterations reached
        return {
            "success": False,
            "final_text": f"Max iterations ({max_iterations}) reached without QA approval",
            "summary": {},
            "iterations": iteration
        }

    def _build_final_text(self, context: Dict, output: Dict) -> str:
        """Build human-readable final text from output."""
        results = output.get('results', {})
        location = output.get('location', {})

        # Extract city name from location data
        city = self._get_city_from_location(location)

        text = ""

        if context['task_type'] == 'annual_yield':
            annual_kwh = results.get('annual_energy_kwh', 0)
            cap_factor = results.get('capacity_factor', 0)
            text = f"A 10 kW system in {city} produces approximately {annual_kwh:,.0f} kWh annually (capacity factor: {cap_factor:.1%})"

        elif context['task_type'] == 'daily_energy':
            daily_kwh = results.get('energy_kwh', 0)
            peak_w = results.get('peak_ac_w', 0)
            text = f"Daily energy in {city}: {daily_kwh:.1f} kWh with peak AC power of {peak_w/1000:.1f} kW"

        else:
            # Generic response
            text = f"Simulation complete. Results: {json.dumps(results, indent=2)}"

        return text

    def _get_city_from_location(self, location: Dict) -> str:
        """
        Extract city name from location data.

        Tries to extract city from timezone string, falls back to coordinates.

        Args:
            location: dict with keys 'lat', 'lon', 'tz', optional 'name'

        Returns:
            City name or coordinate string
        """
        # If name is already provided, use it
        if location.get("name"):
            return location["name"]

        # Extract city from timezone string
        tz = location.get("tz", "")
        if "/" in tz:
            # Split timezone like "Asia/Singapore" or "America/New_York"
            city = tz.split("/")[-1]
            # Replace underscores with spaces for readability
            city = city.replace("_", " ")
            return city

        # Fallback: return coordinates
        lat = location.get("lat", 0)
        lon = location.get("lon", 0)
        return f"({lat:.2f}, {lon:.2f})"

    def interactive_loop(self):
        """Run interactive REPL."""
        # Display ASCII banner
        if self.console:
            from rich.text import Text
            self.console.print(Text(self.HELIO_BANNER, style="bold yellow"))
        else:
            print(self.HELIO_BANNER)

        self.print("[bold cyan]Helio[/bold cyan] — AI Companion for Solar PV Simulation")
        self.print("[dim]Architecture: Router -> SimAgent -> QAAgent[/dim]")
        self.print("\nAsk about yield, tilt, trackers, clipping, temperature, losses…")
        self.print("Type 'help' for examples, 'quit' to exit\n")

        # Test environment
        if not self.executor.test_environment():
            self.print("[red]Warning: Python environment test failed[/red]")
            return

        # Test OpenRouter
        if not self.client.test_connection():
            self.print("[red]Error: Cannot connect to OpenRouter. Check credentials.[/red]")
            return

        # Show runtime info
        self.print("[dim]Runtime: pvlib installed in isolated venv; tool execution enabled[/dim]\n")

        while True:
            try:
                if self.console:
                    user_input = self.console.input("\n[bold green]Helio>[/bold green] ")
                else:
                    user_input = input("\nHelio> ")

                user_input = user_input.strip()

                if user_input.lower() in ['quit', 'exit', 'q']:
                    self.print("\n[bold yellow]Thanks for using Helio! Happy simulating :)[/bold yellow]")
                    break

                if user_input.lower() in ['help', '?']:
                    self._show_help()
                    continue

                if not user_input:
                    continue

                # Run multi-agent loop
                result = self.run_tool_loop(user_input)

                # Display result
                if result["success"]:
                    self.print_panel(result["final_text"], title="Result", style="green")

                    if result.get("summary"):
                        self.print(f"\n[dim]Iterations: {result['iterations']}[/dim]")
                else:
                    self.print_panel(result["final_text"], title="Error", style="red")

            except KeyboardInterrupt:
                self.print("\n\nInterrupted. Type 'quit' to exit.")
                continue
            except Exception as e:
                self.print(f"[red]Error: {e}[/red]")
                import traceback
                traceback.print_exc()

    def _show_help(self):
        """Display help with example queries."""
        help_text = """
[bold cyan]Helio Example Queries[/bold cyan]

[bold]Annual Energy:[/bold]
  • What's the annual energy for a 10kW system in Sydney?
  • How much energy does a 5kW system produce in Berlin?

[bold]Tilt Optimization:[/bold]
  • What's the optimal tilt angle for a system in Tokyo?
  • Compare tilt angles 20°, 30°, and 40° for a 10kW system in Madrid

[bold]Tracking Systems:[/bold]
  • Compare single-axis tracking vs fixed tilt in Phoenix
  • What's the energy gain from tracking in Cape Town?

[bold]System Losses:[/bold]
  • What's the clipping loss for a 10kW DC / 8kW AC inverter?
  • How does temperature affect a 10kW system in Dubai?

[bold]Monthly/Daily Profiles:[/bold]
  • Show monthly energy for a 10kW system in London
  • What's the daily energy profile for June in Sydney?

[dim]Type your question naturally — Helio will figure it out![/dim]
"""
        if self.console:
            self.console.print(help_text)
        else:
            print(help_text)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Helio — AI Companion for Solar PV Simulation",
        epilog="Example: python -m agent.multi_agent_cli --venv sim_runtime/.venv"
    )
    parser.add_argument("--model", default="anthropic/claude-sonnet-4.5", help="OpenRouter model (default: anthropic/claude-sonnet-4.5)")
    parser.add_argument("--venv", help="Path to venv with pvlib")
    parser.add_argument("--log-episodes", action="store_true", help="Log episodes")

    args = parser.parse_args()

    # Auto-detect venv
    venv_path = args.venv
    if not venv_path:
        possible_paths = [
            Path("sim_runtime/.venv"),
            Path("sim_runtime\\.venv"),
        ]
        for path in possible_paths:
            if path.exists():
                venv_path = str(path)
                break

    agent = MultiAgentPV(
        model=args.model,
        venv_path=venv_path,
        log_episodes=args.log_episodes
    )

    agent.interactive_loop()


if __name__ == "__main__":
    main()
