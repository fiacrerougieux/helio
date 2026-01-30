"""
Memory-Centric Orchestrator - Coordinates multi-agent simulation workflow.

Responsibilities:
1. Manage shared memory across agents
2. Orchestrate Plan-Act-Reflect-Revise loop
3. Track conversation history and execution traces
4. Enable context-aware decision making
5. Prevent redundant computations and regressions
"""

import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict, field


@dataclass
class SimulationMemory:
    """Persistent memory structure for multi-agent collaboration."""

    # User input and clarification
    original_prompt: str = ""
    clarified_prompt: Optional[str] = None
    pv_spec: Optional[Dict] = None
    assumptions: List[str] = field(default_factory=list)  # Simple string assumptions (legacy)
    recorded_assumptions: List[Dict[str, Any]] = field(default_factory=list)  # Phase 3.3: Structured assumptions

    # Code generation history
    code_versions: List[Dict[str, Any]] = field(default_factory=list)
    current_code: Optional[str] = None

    # Execution history
    execution_traces: List[Dict[str, Any]] = field(default_factory=list)

    # Error and diagnosis history
    errors: List[Dict[str, Any]] = field(default_factory=list)
    diagnoses: List[Dict[str, Any]] = field(default_factory=list)
    fixes_attempted: List[Dict[str, Any]] = field(default_factory=list)
    error_class_attempts: Dict[str, int] = field(default_factory=dict)  # Phase 3.1: Per-class attempt tracking

    # Results
    successful_output: Optional[Dict[str, Any]] = None

    # Metadata
    iteration_count: int = 0
    start_time: float = field(default_factory=time.time)
    total_execution_time: float = 0.0
    fallback_level: int = 1  # Phase 3.2: Fallback ladder (1=detailed, 2=PVWatts, etc.)

    def increment_error_attempts(self, error_class: str) -> int:
        """Track attempts per error class (Phase 3.1).

        Args:
            error_class: Error class from SimulationExecutorAgent.classify_error()

        Returns:
            Current attempt count for this error class
        """
        self.error_class_attempts[error_class] = \
            self.error_class_attempts.get(error_class, 0) + 1
        return self.error_class_attempts[error_class]

    def should_escalate(self, error_class: str, max_attempts: int = 3) -> bool:
        """Check if error class has exceeded retry limit (Phase 3.1).

        Args:
            error_class: Error class to check
            max_attempts: Maximum allowed attempts before escalation

        Returns:
            True if should escalate to fallback
        """
        return self.error_class_attempts.get(error_class, 0) > max_attempts

    def record_assumption(self, parameter: str, assumed_value: Any, rationale: str):
        """Log defaults picked for reproducibility (Phase 3.3).

        This method records structured assumptions made during simulation setup,
        enabling full reproducibility and transparency in decision-making.

        Args:
            parameter: Name of parameter with assumption (e.g., 'location', 'met_source')
            assumed_value: Value that was assumed
            rationale: Human-readable explanation for why this default was chosen
        """
        self.recorded_assumptions.append({
            'parameter': parameter,
            'assumed_value': str(assumed_value),
            'rationale': rationale,
            'timestamp': time.time(),
            'fallback_level': self.fallback_level
        })

    def to_reproducibility_report(self) -> str:
        """Generate human-readable report of all decisions made (Phase 3.3).

        Returns:
            Markdown-formatted reproducibility report
        """
        report = ["# Simulation Reproducibility Report\n"]

        # Assumptions section
        if self.recorded_assumptions or self.assumptions:
            report.append("## Assumptions Made\n")

            # Structured assumptions (Phase 3.3)
            for i, assumption in enumerate(self.recorded_assumptions, 1):
                report.append(f"{i}. **{assumption['parameter']}** = `{assumption['assumed_value']}`")
                report.append(f"   - Rationale: {assumption['rationale']}")
                if assumption.get('fallback_level', 1) > 1:
                    report.append(f"   - Made at fallback level {assumption['fallback_level']}")
                report.append("")

            # Legacy string assumptions
            if self.assumptions:
                report.append("\nAdditional assumptions:")
                for assumption in self.assumptions:
                    report.append(f"- {assumption}")
                report.append("")

        # Error handling section
        report.append("\n## Error Handling\n")
        report.append(f"- Total iterations: {self.iteration_count}")
        report.append(f"- Fallback level: {self.fallback_level}")

        if self.errors:
            report.append(f"- Errors encountered: {len(self.errors)}")
            for error_class, count in self.error_class_attempts.items():
                report.append(f"  - {error_class}: {count} attempts")

        # Code section
        report.append("\n## Code Generation\n")
        if self.current_code:
            report.append(f"- Final code: {len(self.current_code)} bytes")
            report.append(f"- Code versions generated: {len(self.code_versions)}")

        # Execution section
        if self.successful_output:
            report.append("\n## Execution Summary\n")
            report.append(f"- Status: Success")
            report.append(f"- Total execution time: {self.total_execution_time:.2f}s")
        elif self.errors:
            report.append("\n## Execution Summary\n")
            report.append(f"- Status: Failed after {self.iteration_count} iterations")

        return "\n".join(report)

    def to_dict(self) -> Dict[str, Any]:
        """Convert memory to dict for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SimulationMemory':
        """Load memory from dict."""
        return cls(**data)

    def save(self, path: Path):
        """Save memory to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> 'SimulationMemory':
        """Load memory from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)


class MemoryCentricOrchestrator:
    """Central controller coordinating all agents via shared memory."""

    MAX_ITERATIONS = 10  # Maximum Plan-Act-Reflect-Revise cycles

    # Phase 3.1: Per-error-class attempt limits (from MooseAgent pattern)
    ERROR_CLASS_MAX_ATTEMPTS = {
        'syntax': 2,        # Syntax errors: try twice, then regenerate
        'import': 1,        # Import errors: try once (switch to clearsky if TMY fails)
        'name_error': 2,    # Undefined variables: try twice, then simplify
        'type_error': 2,    # Type mismatches: try twice with conversions
        'attribute_error': 2,  # Missing attributes: try twice
        'value_error': 2,   # Bad values: try twice
        'physical': 3,      # Physical inconsistencies: try 3 times (relax constraints)
        'timeout': 2,       # Timeouts: try twice (reduce time range)
        'runtime': 2,       # General runtime errors: try twice
        'unknown': 1        # Unknown errors: try once, then escalate
    }

    def __init__(
        self,
        clarifier_agent,
        code_builder_agent,
        executor_agent,
        error_diagnosis_agent,
        logger=None
    ):
        """Initialize orchestrator with agent instances.

        Args:
            clarifier_agent: Input Clarifier Agent
            code_builder_agent: Code Builder Agent
            executor_agent: Simulation Executor Agent
            error_diagnosis_agent: Error Diagnosis Agent
            logger: Optional StructuredLogger
        """
        self.clarifier = clarifier_agent
        self.code_builder = code_builder_agent
        self.executor = executor_agent
        self.diagnoser = error_diagnosis_agent
        self.logger = logger

        self.memory = SimulationMemory()

    def run_simulation(
        self,
        user_prompt: str,
        save_memory_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Execute complete simulation workflow with Plan-Act-Reflect-Revise loop.

        Args:
            user_prompt: Natural language simulation request
            save_memory_path: Optional path to save memory trace

        Returns:
            Final result dict with output or error
        """
        # Initialize memory
        self.memory = SimulationMemory(original_prompt=user_prompt)

        if self.logger:
            self.logger.log_event('simulation_start', prompt=user_prompt)

        # Phase 3.3: Check for ambiguity BEFORE attempting simulation
        # Pattern: Human-in-Loop Only for Ambiguity (not for debugging)
        ambiguity_question = self.clarifier.detect_ambiguity(user_prompt)
        if ambiguity_question:
            if self.logger:
                self.logger.log_event('ambiguity_detected', question=ambiguity_question)

            return {
                'success': False,
                'ambiguity_detected': True,
                'clarification_needed': ambiguity_question,
                'reason': 'User input is underspecified. Clarification required before proceeding.'
            }

        # PLAN Phase: Clarify input
        try:
            pv_spec, clarification_summary = self.clarifier.clarify(user_prompt)
            self.memory.pv_spec = pv_spec.model_dump() if hasattr(pv_spec, 'model_dump') else dict(pv_spec)
            self.memory.clarified_prompt = clarification_summary
            self.memory.assumptions = pv_spec.assumptions if hasattr(pv_spec, 'assumptions') else []

            # Phase 3.3: Double-check for ambiguity in generated spec
            post_clarification_ambiguity = self.clarifier.detect_ambiguity(user_prompt, pv_spec)
            if post_clarification_ambiguity:
                if self.logger:
                    self.logger.log_event('ambiguity_detected_post_clarification',
                                         question=post_clarification_ambiguity)

                return {
                    'success': False,
                    'ambiguity_detected': True,
                    'clarification_needed': post_clarification_ambiguity,
                    'reason': 'Generated PV spec is incomplete. User clarification required.'
                }

            # Phase 3.3: Record any assumptions made during clarification
            # (these come from the clarifier's default selection logic)
            if hasattr(pv_spec, 'assumptions') and pv_spec.assumptions:
                for assumption_text in pv_spec.assumptions:
                    # Parse assumption into structured format
                    # For now, record as-is (could be enhanced with structured parsing)
                    if 'location' in assumption_text.lower() or 'lat' in assumption_text.lower():
                        self.memory.record_assumption(
                            'location',
                            f"{pv_spec.site.latitude}, {pv_spec.site.longitude}",
                            assumption_text
                        )
                        # Phase 3.5: Log assumption to structured logger
                        if self.logger:
                            self.logger.log_assumption(
                                'location',
                                f"{pv_spec.site.latitude}, {pv_spec.site.longitude}",
                                assumption_text,
                                self.memory.fallback_level
                            )
                    elif 'clearsky' in assumption_text.lower():
                        self.memory.record_assumption(
                            'met_source',
                            'clearsky',
                            assumption_text
                        )
                        # Phase 3.5: Log assumption
                        if self.logger:
                            self.logger.log_assumption('met_source', 'clearsky', assumption_text, self.memory.fallback_level)
                    elif 'tilt' in assumption_text.lower():
                        self.memory.record_assumption(
                            'tilt',
                            pv_spec.system.tilt_deg,
                            assumption_text
                        )
                        # Phase 3.5: Log assumption
                        if self.logger:
                            self.logger.log_assumption('tilt', pv_spec.system.tilt_deg, assumption_text, self.memory.fallback_level)
                    elif 'azimuth' in assumption_text.lower():
                        self.memory.record_assumption(
                            'azimuth',
                            pv_spec.system.azimuth_deg,
                            assumption_text
                        )
                        # Phase 3.5: Log assumption
                        if self.logger:
                            self.logger.log_assumption('azimuth', pv_spec.system.azimuth_deg, assumption_text, self.memory.fallback_level)
                    # Could add more structured parsing here

            if self.logger:
                self.logger.log_event('clarification_complete',
                                     task_type=str(pv_spec.output.task_type),
                                     assumptions_recorded=len(self.memory.recorded_assumptions))
        except Exception as e:
            return self._handle_fatal_error('clarification', str(e))

        # Main Plan-Act-Reflect-Revise Loop
        for iteration in range(self.MAX_ITERATIONS):
            self.memory.iteration_count = iteration + 1

            if self.logger:
                self.logger.log_event('iteration_start', iteration=iteration + 1)

            # ACT Phase: Generate and execute code
            result = self._execute_iteration(pv_spec)

            if result['success']:
                # Success! Store result and exit
                self.memory.successful_output = result['output']
                self.memory.total_execution_time = time.time() - self.memory.start_time

                if save_memory_path:
                    self.memory.save(save_memory_path)

                if self.logger:
                    self.logger.log_event('simulation_success',
                                         iterations=self.memory.iteration_count,
                                         total_time=self.memory.total_execution_time,
                                         assumptions_made=len(self.memory.recorded_assumptions))

                return {
                    'success': True,
                    'output': result['output'],
                    'iterations': self.memory.iteration_count,
                    'assumptions': self.memory.assumptions,  # Legacy string assumptions
                    'recorded_assumptions': self.memory.recorded_assumptions,  # Phase 3.3: Structured assumptions
                    'reproducibility_report': self.memory.to_reproducibility_report(),  # Phase 3.3
                    'clarification': self.memory.clarified_prompt,
                    'fallback_level': self.memory.fallback_level
                }

            # REFLECT Phase: Diagnose failure
            error_context = self.executor.extract_error_context(result)
            error_class = error_context['error_class']

            # Phase 3.1: Track error class attempts
            attempts = self.memory.increment_error_attempts(error_class)
            max_allowed = self.ERROR_CLASS_MAX_ATTEMPTS.get(error_class, 3)

            # Check if we should escalate (too many attempts)
            if self.memory.should_escalate(error_class, max_allowed):
                if self.logger:
                    self.logger.log_event('error_escalation',
                                         error_class=error_class,
                                         attempts=attempts,
                                         reason='max_attempts_exceeded')

                escalation_result = self._handle_error_escalation(error_class, attempts, "Max attempts exceeded")

                # Phase 3.2: Check if fallback retry is requested
                if escalation_result.get('fallback_retry'):
                    # Reset error counters for new fallback level
                    self.memory.error_class_attempts = {}
                    self.diagnoser.clear_fix_history()

                    if self.logger:
                        self.logger.log_event('fallback_retry',
                                             level=escalation_result['new_level'],
                                             message=escalation_result['message'])

                    # Continue iteration with new fallback level
                    continue
                else:
                    # No fallback available, return error
                    return escalation_result

            # Diagnose with no-repeat patch guard
            diagnosis = self._diagnose_failure(result)
            self.memory.diagnoses.append(diagnosis)

            # Check if diagnosis flagged escalation (no novel fixes)
            if diagnosis.get('escalate'):
                if self.logger:
                    self.logger.log_event('error_escalation',
                                         error_class=error_class,
                                         attempts=attempts,
                                         reason=diagnosis.get('escalate_reason', 'no_novel_fixes'))

                escalation_result = self._handle_error_escalation(error_class, attempts, diagnosis.get('escalate_reason', 'No novel fixes'))

                # Phase 3.2: Check if fallback retry is requested
                if escalation_result.get('fallback_retry'):
                    # Reset error counters for new fallback level
                    self.memory.error_class_attempts = {}
                    self.diagnoser.clear_fix_history()

                    if self.logger:
                        self.logger.log_event('fallback_retry',
                                             level=escalation_result['new_level'],
                                             message=escalation_result['message'])

                    # Continue iteration with new fallback level
                    continue
                else:
                    # No fallback available, return error
                    return escalation_result

            # REVISE Phase: Apply fixes and record
            revision_applied = self._apply_revisions(pv_spec, diagnosis, error_class)

            if not revision_applied:
                # No fixes available, give up
                break

        # Max iterations reached or no fixes available
        return self._handle_max_iterations()

    def _execute_iteration(self, pv_spec) -> Dict[str, Any]:
        """Execute one Plan-Act iteration.

        Args:
            pv_spec: Current PV specification

        Returns:
            Execution result
        """
        # Generate code based on fallback level (Phase 3.2)
        try:
            fallback_level = self.memory.fallback_level

            if fallback_level == 1:
                # Level 1: Detailed pvlib model (default)
                code = self.code_builder.build_code(pv_spec)
            elif fallback_level == 2:
                # Level 2: Simplified PVWatts
                code = self.code_builder.build_pvwatts_simple(pv_spec)
            elif fallback_level == 3:
                # Level 3: Constant irradiance approximation
                code = self.code_builder.build_constant_irrad(pv_spec)
            else:
                # Level 4+: Should not reach here
                raise ValueError(f"Invalid fallback level: {fallback_level}")

            self.memory.current_code = code
            self.memory.code_versions.append({
                'iteration': self.memory.iteration_count,
                'code': code,
                'fallback_level': fallback_level,
                'timestamp': time.time()
            })
        except Exception as e:
            return {
                'success': False,
                'error': f'Code generation failed: {str(e)}',
                'stage': 'code_generation'
            }

        # Execute code
        exec_result = self.executor.execute_with_monitoring(
            code=code,
            timeout=60,
            enforce_determinism=False
        )

        # Log execution
        self.memory.execution_traces.append({
            'iteration': self.memory.iteration_count,
            'result': exec_result,
            'timestamp': time.time()
        })

        if not exec_result['success']:
            # Extract and store error
            error_context = self.executor.extract_error_context(exec_result)
            self.memory.errors.append({
                'iteration': self.memory.iteration_count,
                'context': error_context,
                'result': exec_result
            })

        return exec_result

    def _diagnose_failure(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Diagnose execution failure.

        Args:
            result: Failed execution result

        Returns:
            Diagnosis dict
        """
        # Get error context
        error_context = self.executor.extract_error_context(result)

        # Get previous fixes for learning
        previous_fixes = [f['diagnosis'].get('fixes', []) for f in self.memory.diagnoses]

        # Diagnose
        diagnosis = self.diagnoser.diagnose(
            code=self.memory.current_code,
            error_context=error_context,
            previous_fixes=previous_fixes
        )

        if self.logger:
            self.logger.log_event('diagnosis_complete',
                                 error_class=error_context['error_class'],
                                 problem_type=diagnosis['problem_type'])

        return diagnosis

    def _apply_revisions(self, pv_spec, diagnosis: Dict[str, Any], error_class: str) -> bool:
        """Apply fixes from diagnosis.

        Args:
            pv_spec: Current PV spec
            diagnosis: Diagnosis with suggested fixes
            error_class: Error class for tracking fix application

        Returns:
            True if revision applied, False if no fixes available
        """
        fixes = diagnosis.get('fixes', [])

        if not fixes:
            return False

        # Phase 3.1: Record fix application to prevent re-application
        for fix in fixes:
            self.diagnoser.record_fix_applied(fix, error_class)

        # For Phase 2, we apply simple heuristic fixes
        # Future: Use Input Rewriter Agent to modify spec/code based on fixes

        # Log fix attempt
        self.memory.fixes_attempted.append({
            'iteration': self.memory.iteration_count,
            'fixes': fixes,
            'timestamp': time.time()
        })

        # For now, just record the attempt
        # In full implementation, this would modify pv_spec or code
        return True  # Indicate we tried to apply fixes

    def _handle_error_escalation(self, error_class: str, attempts: int, reason: str) -> Dict[str, Any]:
        """Handle error escalation when max attempts exceeded (Phase 3.1).

        Args:
            error_class: Error class that exceeded limits
            attempts: Number of attempts made
            reason: Reason for escalation

        Returns:
            Error result with escalation info
        """
        if self.logger:
            self.logger.log_event('error_escalation',
                                 error_class=error_class,
                                 attempts=attempts,
                                 reason=reason,
                                 fallback_level=self.memory.fallback_level)

        # Get error history summary
        error_summary = {
            error_class: attempts
            for error_class, attempts in self.memory.error_class_attempts.items()
        }

        # Phase 3.2: Implement fallback ladder (5 levels)
        current_level = self.memory.fallback_level

        if current_level == 1:
            # Level 1 -> Level 2: Try PVWatts simplified model
            self.memory.fallback_level = 2
            self.memory.assumptions.append(
                f'Fallback to PVWatts: Detailed model failed after {attempts} {error_class} errors'
            )

            if self.logger:
                self.logger.log_event('fallback_transition',
                                     from_level=1,
                                     to_level=2,
                                     reason=f'{error_class} errors')

            # Signal to retry with simplified model
            return {
                'success': False,
                'fallback_retry': True,
                'new_level': 2,
                'message': 'Retrying with simplified PVWatts model',
                'reason': reason
            }

        elif current_level == 2:
            # Level 2 -> Level 3: Try constant irradiance approximation
            self.memory.fallback_level = 3
            self.memory.assumptions.append(
                f'Fallback to constant irradiance: PVWatts failed'
            )

            if self.logger:
                self.logger.log_event('fallback_transition',
                                     from_level=2,
                                     to_level=3,
                                     reason=f'{error_class} errors')

            return {
                'success': False,
                'fallback_retry': True,
                'new_level': 3,
                'message': 'Retrying with constant irradiance approximation',
                'reason': reason
            }

        elif current_level == 3:
            # Level 3 -> Level 4: Ask user (Phase 3.3 will implement this)
            self.memory.fallback_level = 4

            if self.logger:
                self.logger.log_event('fallback_user_prompt_needed',
                                     error_summary=error_summary)

            return {
                'success': False,
                'human_in_loop_required': True,
                'question': f"The simulation failed with {error_class} errors even after simplification. Would you like to:\n1. Provide more specific inputs\n2. Accept the rough estimate from level 3\n3. Abandon this query",
                'error_summary': error_summary,
                'reason': reason
            }

        else:
            # Level 4 -> Level 5: Fail gracefully
            self.memory.fallback_level = 5

            if self.logger:
                self.logger.log_event('fallback_exhausted',
                                     iterations=self.memory.iteration_count,
                                     error_summary=error_summary)

            return {
                'success': False,
                'error': 'Simulation could not complete after exhausting all fallback options',
                'error_class': error_class,
                'attempts': attempts,
                'reason': reason,
                'error_summary': error_summary,
                'iterations': self.memory.iteration_count,
                'fallback_level': 5,
                'assumptions': self.memory.assumptions,
                'recommendations': [
                    'All simplification levels failed',
                    'Try a different location or system configuration',
                    'Verify your inputs are realistic',
                    'Contact support if this persists'
                ]
            }

    def _handle_fatal_error(self, stage: str, error: str) -> Dict[str, Any]:
        """Handle fatal errors that prevent simulation."""
        if self.logger:
            self.logger.log_event('fatal_error', stage=stage, error=error)

        return {
            'success': False,
            'error': f'{stage} failed: {error}',
            'stage': stage
        }

    def _handle_max_iterations(self) -> Dict[str, Any]:
        """Handle case where max iterations reached."""
        if self.logger:
            self.logger.log_event('max_iterations_reached',
                                 iterations=self.memory.iteration_count)

        # Return last error and diagnosis
        last_error = self.memory.errors[-1] if self.memory.errors else None
        last_diagnosis = self.memory.diagnoses[-1] if self.memory.diagnoses else None

        return {
            'success': False,
            'error': f'Failed to complete simulation after {self.memory.iteration_count} iterations',
            'last_error': last_error,
            'last_diagnosis': last_diagnosis,
            'iterations': self.memory.iteration_count
        }

    def get_memory(self) -> SimulationMemory:
        """Get current simulation memory."""
        return self.memory

    def reset_memory(self):
        """Reset memory for new simulation."""
        self.memory = SimulationMemory()
