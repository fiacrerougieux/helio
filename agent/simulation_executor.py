"""
Simulation Executor Agent - Executes PV simulation code with monitoring.

Extends PythonExecutor with Phase 2 capabilities:
1. Physical consistency monitoring (conservation, residuals, bounds)
2. Execution trace logging
3. Performance metrics collection
4. Error classification
"""

import json
import re
from typing import Dict, Any, Optional, List
from pathlib import Path
from agent.executor import PythonExecutor


class SimulationExecutorAgent:
    """Agent that executes simulation code with physics-aware monitoring."""

    def __init__(self, venv_path: str = None, logger=None, enable_hardening: bool = True):
        """Initialize Simulation Executor Agent.

        Args:
            venv_path: Path to Python venv with pvlib installed
            logger: Optional StructuredLogger
            enable_hardening: Enable security hardening
        """
        self.executor = PythonExecutor(
            venv_path=venv_path,
            logger=logger,
            enable_hardening=enable_hardening
        )
        self.logger = logger
        self.execution_history: List[Dict[str, Any]] = []

    def execute_with_monitoring(
        self,
        code: str,
        timeout: int = 60,
        enforce_determinism: bool = False
    ) -> Dict[str, Any]:
        """Execute simulation code with physical consistency monitoring.

        Args:
            code: Python code to execute
            timeout: Timeout in seconds
            enforce_determinism: Enable deterministic execution

        Returns:
            Dict with:
                - success: bool
                - output: dict (if successful)
                - stdout: str
                - stderr: str
                - error: str (if failed)
                - execution_time: float
                - physical_checks: dict (consistency checks)
                - preflight_failed: bool (syntax/security check failed)
        """
        # Execute using base executor
        result = self.executor.execute_with_json_output(
            code=code,
            timeout=timeout,
            enforce_determinism=enforce_determinism
        )

        # Add physical consistency checks
        if result['success']:
            physical_checks = self._check_physical_consistency(result['output'])
            result['physical_checks'] = physical_checks

            # If physical checks fail, mark as unsuccessful
            if not physical_checks['all_passed']:
                result['success'] = False
                result['error'] = f"Physical consistency check failed: {physical_checks['failures']}"

        # Log execution
        self.execution_history.append({
            'code_hash': hash(code),
            'result': result,
            'timestamp': __import__('time').time()
        })

        if self.logger:
            self.logger.log_event(
                'code_execution',
                success=result['success'],
                execution_time=result.get('execution_time', 0),
                physical_checks_passed=result.get('physical_checks', {}).get('all_passed', None)
            )

        return result

    def _check_physical_consistency(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """Check physical plausibility of simulation results with PV domain knowledge.

        Phase 3.4: Enhanced domain constraints from SimNDT "Ground AI" pattern.

        Args:
            output: Simulation output dictionary

        Returns:
            Dict with:
                - all_passed: bool
                - failures: list of failure messages
                - warnings: list of warnings
        """
        failures = []
        warnings = []

        # Phase 3.4 Check 1: Specific yield (kWh/kWp) validation
        # Typical range: 800-2200 kWh/kWp depending on location and system quality
        # Lower bound: ~500 (high latitude, poor conditions)
        # Upper bound: ~2500 (tracking, excellent conditions)
        if 'annual_kwh' in output and 'system' in output:
            # Get DC capacity in kW (handle both dc_capacity_w in watts and dc_kw)
            if 'dc_capacity_w' in output['system']:
                dc_kw = output['system']['dc_capacity_w'] / 1000.0
            elif 'dc_kw' in output['system']:
                dc_kw = output['system']['dc_kw']
            else:
                dc_kw = 1.0  # Default 1 kW

            if dc_kw > 0:
                specific_yield = output['annual_kwh'] / dc_kw  # kWh/kWp

                if specific_yield < 400:
                    failures.append(f"Specific yield {specific_yield:.0f} kWh/kWp is too low (expect 800-2200 for typical systems)")
                elif specific_yield > 3500:
                    failures.append(f"Specific yield {specific_yield:.0f} kWh/kWp is too high (expect 800-2200 for typical systems)")
                elif specific_yield < 800:
                    warnings.append(f"Low specific yield {specific_yield:.0f} kWh/kWp (typical: 800-2200). Check location or system losses.")
                elif specific_yield > 2200:
                    warnings.append(f"High specific yield {specific_yield:.0f} kWh/kWp (typical: 800-2200). Verify irradiance data or tracking system.")

        # Check 1 (legacy): No negative energy
        if 'annual_kwh' in output:
            if output['annual_kwh'] < 0:
                failures.append("Negative annual energy")
            elif output['annual_kwh'] == 0:
                warnings.append("Zero annual energy (check if simulation ran)")

        # Phase 3.4 Check 2: Enhanced capacity factor bounds
        # Solar PV typical range: 0.10-0.45
        # Fixed tilt: 0.10-0.25, Single-axis tracking: 0.20-0.35, Dual-axis tracking: 0.25-0.45
        if 'capacity_factor' in output:
            cf = output['capacity_factor']
            if cf < 0 or cf > 1:
                failures.append(f"Capacity factor {cf:.3f} outside physical bounds [0, 1]")
            elif cf < 0.08:
                failures.append(f"Capacity factor {cf:.3f} too low (solar typical: 0.10-0.45)")
            elif cf > 0.50:
                failures.append(f"Capacity factor {cf:.3f} too high (solar typical: 0.10-0.45, even for dual-axis tracking)")
            elif cf < 0.10:
                warnings.append(f"Low capacity factor {cf:.3f} (typical: 0.10-0.45). Check system orientation or shading.")
            elif cf > 0.45:
                warnings.append(f"High capacity factor {cf:.3f} (typical: 0.10-0.45). Verify system configuration.")

        # Phase 3.4 Check 3: Tilt angle validation
        # Valid range: 0-90° (0=horizontal, 90=vertical)
        if 'system' in output:
            tilt = output['system'].get('tilt_deg', output['system'].get('tilt', None))
            if tilt is not None:
                if tilt < 0 or tilt > 90:
                    failures.append(f"Tilt angle {tilt}° outside valid range [0, 90]")

        # Phase 3.4 Check 4: System losses validation
        # Typical range: 10-20% for well-designed systems
        if 'system' in output:
            losses = output['system'].get('losses_percent', None)
            if losses is not None:
                if losses < 0 or losses > 100:
                    failures.append(f"System losses {losses}% outside valid range [0, 100]")
                elif losses > 50:
                    warnings.append(f"High system losses {losses}% (typical: 10-20%). Verify loss model.")
                elif losses < 5:
                    warnings.append(f"Low system losses {losses}% (typical: 10-20%). May be overly optimistic.")

        # Phase 3.4 Check 5: DC > AC power check (inverter clipping)
        if 'peak_dc_w' in output and 'peak_ac_w' in output:
            if output['peak_ac_w'] > output['peak_dc_w']:
                failures.append("Peak AC power exceeds peak DC power (violates physics)")

        # Check 3 (legacy): Peak AC power reasonableness
        if 'peak_ac_w' in output:
            peak = output['peak_ac_w']
            if peak < 0:
                failures.append("Negative peak AC power")
            elif peak == 0:
                warnings.append("Zero peak AC power")

        # Check 4 (legacy): System comparison consistency
        if 'systems' in output:
            for i, sys in enumerate(output['systems']):
                if 'annual_kwh' in sys and sys['annual_kwh'] < 0:
                    failures.append(f"System {i} ({sys.get('name', 'unnamed')}) has negative energy")
                if 'capacity_factor' in sys:
                    cf = sys['capacity_factor']
                    if cf < 0 or cf > 1:
                        failures.append(f"System {i} capacity factor {cf} out of bounds")

        # Check 5 (legacy): Monthly profile sum consistency
        if 'monthly_kwh' in output:
            monthly_sum = sum(output['monthly_kwh'])
            if 'annual_kwh' in output:
                if abs(monthly_sum - output['annual_kwh']) / output['annual_kwh'] > 0.01:
                    failures.append(
                        f"Monthly sum ({monthly_sum:.1f}) != annual total ({output['annual_kwh']:.1f})"
                    )

        return {
            'all_passed': len(failures) == 0,
            'failures': failures,
            'warnings': warnings
        }

    def classify_error(self, result: Dict[str, Any]) -> str:
        """Classify execution error type for diagnosis.

        Args:
            result: Execution result dict

        Returns:
            Error class: 'syntax', 'runtime', 'import', 'timeout', 'physical', 'unknown'
        """
        if result['success']:
            return 'none'

        error = result.get('error', '')
        stderr = result.get('stderr', '')

        # Preflight failures (AST checks)
        if result.get('preflight_failed', False):
            if 'Syntax error' in error:
                return 'syntax'
            if 'Forbidden' in error:
                return 'security'

        # Timeout
        if 'timeout' in error.lower() or 'timed out' in error.lower():
            return 'timeout'

        # Import errors
        if 'ImportError' in stderr or 'ModuleNotFoundError' in stderr:
            return 'import'

        # Physical consistency
        if 'Physical consistency check failed' in error:
            return 'physical'

        # Runtime errors (from stderr)
        if stderr:
            if 'NameError' in stderr:
                return 'name_error'
            if 'TypeError' in stderr:
                return 'type_error'
            if 'ValueError' in stderr:
                return 'value_error'
            if 'AttributeError' in stderr:
                return 'attribute_error'
            if 'KeyError' in stderr:
                return 'key_error'
            if 'ZeroDivisionError' in stderr:
                return 'math_error'
            if 'RuntimeError' in stderr or 'Exception' in stderr:
                return 'runtime'

        return 'unknown'

    def extract_error_context(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract detailed error context for diagnosis.

        Args:
            result: Execution result dict

        Returns:
            Context dict with error details
        """
        error_class = self.classify_error(result)
        stderr = result.get('stderr', '')
        error_msg = result.get('error', '')

        context = {
            'error_class': error_class,
            'error_message': error_msg,
            'stderr': stderr,
            'line_number': None,
            'variable_name': None,
            'traceback': None
        }

        # Extract line number from traceback
        line_match = re.search(r'line (\d+)', stderr)
        if line_match:
            context['line_number'] = int(line_match.group(1))

        # Extract variable name from NameError
        if error_class == 'name_error':
            name_match = re.search(r"name '([^']+)' is not defined", stderr)
            if name_match:
                context['variable_name'] = name_match.group(1)

        # Extract full traceback
        if 'Traceback' in stderr:
            traceback_start = stderr.index('Traceback')
            context['traceback'] = stderr[traceback_start:]

        # Extract physical check failures
        if error_class == 'physical':
            if 'physical_checks' in result:
                context['physical_failures'] = result['physical_checks']['failures']

        return context

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history for memory-based learning.

        Returns:
            List of execution records
        """
        return self.execution_history

    def clear_history(self):
        """Clear execution history."""
        self.execution_history = []
