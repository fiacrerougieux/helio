"""
Error Diagnosis Agent - Analyzes execution failures and proposes corrections.

Responsibilities:
1. Interpret runtime errors in physical/numerical terms
2. Propose targeted physics-aware corrections
3. Generate diagnostic hints for other agents
4. Learn from error-fix patterns in memory
"""

import json
from typing import Dict, Any, List, Optional, Tuple


class ErrorDiagnosisAgent:
    """Agent that diagnoses simulation failures and proposes fixes."""

    DIAGNOSIS_PROMPT_TEMPLATE = """You are a PV simulation error diagnosis expert.

A simulation execution failed. Your job is to:
1. Analyze the error in physical/numerical terms
2. Propose specific, targeted fixes
3. Prioritize fixes that address root causes

ERROR CONTEXT:
Error Class: {error_class}
Error Message: {error_message}
Line Number: {line_number}
Stderr Output:
{stderr}

CODE THAT FAILED:
```python
{code}
```

PREVIOUS FIXES ATTEMPTED:
{previous_fixes}

Provide your diagnosis in JSON format:
{{
  "root_cause": "Brief description of the underlying issue",
  "problem_type": "one of: syntax, name_error, type_mismatch, physical_inconsistency, numerical_instability, missing_data, logic_error",
  "fixes": [
    {{
      "description": "What this fix does",
      "priority": "high/medium/low",
      "code_change": "Specific code to change or add",
      "rationale": "Why this fix addresses the root cause"
    }}
  ],
  "explanation": "Student-friendly explanation of what went wrong"
}}

Focus on physics-aware fixes like:
- Mesh resolution adjustments
- Solver tolerance changes
- Boundary condition corrections
- Temperature model parameter fixes
- Data range/timezone corrections
"""

    def __init__(self, llm_client=None):
        """Initialize Error Diagnosis Agent.

        Args:
            llm_client: LLM client for dynamic diagnosis
        """
        self.llm_client = llm_client
        self.fix_history: List[Dict[str, Any]] = []
        self.applied_fix_hashes: set = set()  # No-repeat patch guard

    def diagnose(
        self,
        code: str,
        error_context: Dict[str, Any],
        previous_fixes: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Diagnose execution failure and propose fixes.

        Args:
            code: Code that failed
            error_context: Error details from SimulationExecutorAgent
            previous_fixes: Previously attempted fixes (for learning)

        Returns:
            Diagnosis dict with root_cause, fixes, explanation
        """
        error_class = error_context['error_class']

        # Use rule-based diagnosis for common cases, LLM for complex ones
        if error_class in ['syntax', 'import', 'security', 'timeout']:
            diagnosis = self._diagnose_simple_error(code, error_context)
        elif error_class == 'physical':
            diagnosis = self._diagnose_physical_error(code, error_context)
        elif error_class in ['name_error', 'attribute_error', 'type_error']:
            diagnosis = self._diagnose_code_error(code, error_context)
        else:
            # Complex errors need LLM
            diagnosis = self._diagnose_with_llm(code, error_context, previous_fixes or [])

        # Filter out already-tried fixes (no-repeat patch guard)
        fixes = diagnosis.get('fixes', [])
        novel_fixes = []

        for fix in fixes:
            fix_hash = self._hash_fix(fix, error_class)
            if fix_hash not in self.applied_fix_hashes:
                novel_fixes.append(fix)

        diagnosis['fixes'] = novel_fixes

        # If no novel fixes, mark for escalation
        if fixes and not novel_fixes:
            diagnosis['escalate'] = True
            diagnosis['escalate_reason'] = 'All suggested fixes already attempted'

        # Log diagnosis
        self.fix_history.append({
            'error_class': error_class,
            'diagnosis': diagnosis,
            'timestamp': __import__('time').time()
        })

        return diagnosis

    def _diagnose_simple_error(
        self,
        code: str,
        error_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rule-based diagnosis for simple errors."""

        error_class = error_context['error_class']
        error_msg = error_context['error_message']

        if error_class == 'syntax':
            return {
                'root_cause': 'Python syntax error in generated code',
                'problem_type': 'syntax',
                'fixes': [{
                    'description': 'Fix syntax error',
                    'priority': 'high',
                    'code_change': f'Review line {error_context["line_number"]} for syntax issues',
                    'rationale': 'Code must be syntactically valid Python'
                }],
                'explanation': 'The generated code has a syntax error that prevents execution.'
            }

        elif error_class == 'import':
            return {
                'root_cause': 'Missing or forbidden module import',
                'problem_type': 'missing_data',
                'fixes': [{
                    'description': 'Check module availability in venv',
                    'priority': 'high',
                    'code_change': 'Ensure required modules are installed: pvlib, pandas, numpy',
                    'rationale': 'Simulation requires pvlib ecosystem'
                }],
                'explanation': 'A required Python module is not available in the execution environment.'
            }

        elif error_class == 'timeout':
            return {
                'root_cause': 'Execution exceeded time limit',
                'problem_type': 'numerical_instability',
                'fixes': [
                    {
                        'description': 'Reduce time range',
                        'priority': 'high',
                        'code_change': 'Use smaller date range or coarser frequency',
                        'rationale': 'Large time ranges take longer to compute'
                    },
                    {
                        'description': 'Optimize computation',
                        'priority': 'medium',
                        'code_change': 'Use vectorized operations, avoid loops',
                        'rationale': 'Vectorization improves performance'
                    }
                ],
                'explanation': 'The simulation took too long to complete. Try reducing the time range or using a coarser time resolution.'
            }

        return {
            'root_cause': 'Unknown error type',
            'problem_type': 'logic_error',
            'fixes': [],
            'explanation': error_msg
        }

    def _diagnose_physical_error(
        self,
        code: str,
        error_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Diagnose physical consistency failures."""

        physical_failures = error_context.get('physical_failures', [])
        fixes = []

        for failure in physical_failures:
            if 'Negative' in failure:
                fixes.append({
                    'description': 'Fix negative energy calculation',
                    'priority': 'high',
                    'code_change': 'Check for sign errors in power calculations or coordinate system issues',
                    'rationale': 'Energy production cannot be negative'
                })

            elif 'Capacity factor' in failure and 'outside' in failure:
                fixes.append({
                    'description': 'Correct capacity factor calculation',
                    'priority': 'high',
                    'code_change': 'Verify capacity factor = energy_kwh / (dc_capacity_kw * hours)',
                    'rationale': 'Capacity factor must be between 0 and 1'
                })

            elif 'Monthly sum' in failure:
                fixes.append({
                    'description': 'Fix monthly-annual energy mismatch',
                    'priority': 'medium',
                    'code_change': 'Ensure monthly values sum to annual total',
                    'rationale': 'Conservation of energy: monthly must sum to annual'
                })

        return {
            'root_cause': 'Physical conservation or bounds violation',
            'problem_type': 'physical_inconsistency',
            'fixes': fixes,
            'explanation': f'The simulation results violate physical constraints: {", ".join(physical_failures)}'
        }

    def _diagnose_code_error(
        self,
        code: str,
        error_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Diagnose Python runtime errors (NameError, AttributeError, etc.)."""

        error_class = error_context['error_class']
        stderr = error_context['stderr']
        var_name = error_context.get('variable_name')

        if error_class == 'name_error' and var_name:
            # Check if it's a common pvlib variable
            pvlib_suggestions = {
                'dni': 'Direct Normal Irradiance - use irrad_data["dni"]',
                'ghi': 'Global Horizontal Irradiance - use irrad_data["ghi"]',
                'dhi': 'Diffuse Horizontal Irradiance - use irrad_data["dhi"]',
                'poa': 'Plane of Array - calculate with get_total_irradiance()',
                'temp_cell': 'Cell temperature - calculate with sapm_cell() or pvsyst_cell()'
            }

            suggestion = pvlib_suggestions.get(var_name, f'Variable "{var_name}" not defined')

            return {
                'root_cause': f'Undefined variable: {var_name}',
                'problem_type': 'name_error',
                'fixes': [{
                    'description': f'Define {var_name}',
                    'priority': 'high',
                    'code_change': suggestion,
                    'rationale': 'All variables must be defined before use'
                }],
                'explanation': f'Variable "{var_name}" is used but not defined. {suggestion}'
            }

        elif error_class == 'attribute_error':
            # Try to extract the attribute name
            # Error msg: module 'pvlib' has no attribute 'foo'
            import re
            match = re.search(r"attribute '([^']+)'", error_context.get('error_message', ''))
            missing_symbols = []
            if match:
                attr = match.group(1)
                # Heuristic: if variable name was 'pvlib', assume 'pvlib.attr'
                # But error context doesn't give us the object name easily without parsing code.
                # However, if the error message says "module 'pvlib'...", we know it's pvlib.
                if "module 'pvlib'" in error_context.get('error_message', ''):
                    missing_symbols.append(f"pvlib.{attr}")
            
            return {
                'root_cause': 'Accessing non-existent attribute or method',
                'problem_type': 'type_mismatch',
                'missing_symbols': missing_symbols,
                'fixes': [{
                    'description': 'Check object type and available methods',
                    'priority': 'high',
                    'code_change': 'Verify object type and consult pvlib documentation',
                    'rationale': 'Attributes must exist on the object'
                }],
                'explanation': 'Trying to access an attribute or method that doesn\'t exist on this object.'
            }

        elif error_class == 'type_error':
            return {
                'root_cause': 'Type mismatch in operation or function call',
                'problem_type': 'type_mismatch',
                'fixes': [{
                    'description': 'Convert types appropriately',
                    'priority': 'high',
                    'code_change': 'Check function argument types (e.g., float() for numbers, pd.Series for arrays)',
                    'rationale': 'Function arguments must match expected types'
                }],
                'explanation': 'A function received the wrong type of argument.'
            }

        return {
            'root_cause': f'{error_class} in code',
            'problem_type': 'logic_error',
            'fixes': [],
            'explanation': stderr[:200]  # First 200 chars of stderr
        }

    def _diagnose_with_llm(
        self,
        code: str,
        error_context: Dict[str, Any],
        previous_fixes: List[Dict]
    ) -> Dict[str, Any]:
        """Use LLM for complex error diagnosis."""

        if not self.llm_client:
            # Fallback to simple diagnosis
            return {
                'root_cause': 'Complex error requiring LLM diagnosis',
                'problem_type': 'logic_error',
                'fixes': [{
                    'description': 'Manual review needed',
                    'priority': 'high',
                    'code_change': 'Review error and fix manually',
                    'rationale': 'Error too complex for rule-based diagnosis'
                }],
                'explanation': error_context.get('error_message', 'Unknown error')
            }

        # Format prompt
        previous_fixes_text = json.dumps(previous_fixes, indent=2) if previous_fixes else "None"

        prompt = self.DIAGNOSIS_PROMPT_TEMPLATE.format(
            error_class=error_context['error_class'],
            error_message=error_context['error_message'],
            line_number=error_context.get('line_number', 'Unknown'),
            stderr=error_context.get('stderr', '')[:500],  # Limit stderr
            code=code[:1000],  # Limit code
            previous_fixes=previous_fixes_text
        )

        # Call LLM
        try:
            response = self.llm_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.0
            )
            diagnosis = json.loads(response)
            return diagnosis
        except Exception as e:
            return {
                'root_cause': 'LLM diagnosis failed',
                'problem_type': 'logic_error',
                'fixes': [],
                'explanation': f'Could not diagnose with LLM: {str(e)}'
            }

    def suggest_clarifier_revision(self, diagnosis: Dict[str, Any]) -> Optional[str]:
        """Determine if error requires clarifier revision.

        Args:
            diagnosis: Diagnosis dict

        Returns:
            Hint for Input Rewriter Agent, or None if not needed
        """
        problem_type = diagnosis['problem_type']

        # Errors that suggest spec-level issues
        if problem_type in ['missing_data', 'physical_inconsistency']:
            if diagnosis['fixes']:
                return diagnosis['fixes'][0]['description']

        return None

    def _hash_fix(self, fix: Dict[str, Any], error_class: str) -> str:
        """Hash a fix based on its code_change and error_class.

        Args:
            fix: Fix dict with code_change
            error_class: Error class this fix addresses

        Returns:
            Hash string for deduplication
        """
        import hashlib
        # Combine error class and code change for uniqueness
        content = f"{error_class}::{fix.get('code_change', '')}"
        return hashlib.md5(content.encode()).hexdigest()

    def record_fix_applied(self, fix: Dict[str, Any], error_class: str):
        """Mark a fix as applied to prevent re-application.

        Args:
            fix: Fix dict that was applied
            error_class: Error class the fix addressed
        """
        fix_hash = self._hash_fix(fix, error_class)
        self.applied_fix_hashes.add(fix_hash)

    def clear_fix_history(self):
        """Clear fix history and applied fix hashes (for new simulation)."""
        self.fix_history = []
        self.applied_fix_hashes = set()
