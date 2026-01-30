"""
Safe Python code executor for PV simulation code.
Runs in isolated venv with pvlib installed.
Includes syntax preflight checking and import allowlist.

Security Features (Phase 1 Hardening):
- AST-based blocking of eval/exec/compile
- Dunder attribute access prevention
- Resource limits (CPU, memory, file size on Unix)
- Output size limits
- Optional determinism enforcement
"""

import subprocess
import json
import tempfile
import os
import ast
import time
import hashlib
from pathlib import Path
from typing import Dict, Tuple, List, Optional

# Import resource module for Unix-like systems
try:
    import resource
    RESOURCE_AVAILABLE = True
except ImportError:
    RESOURCE_AVAILABLE = False


class PythonExecutor:
    # Allowed imports for PV simulation (security + reliability)
    ALLOWED_IMPORTS = {
        'pvlib', 'pandas', 'numpy', 'scipy', 'matplotlib', 'json',
        'math', 'datetime', 'pytz', 'dateutil', 'warnings',
        'random', 'time'  # Safe for simulations, used in determinism wrapper
    }

    # Safe dunder attributes that are allowed
    SAFE_DUNDERS = {'__name__', '__doc__', '__version__', '__file__'}

    # Forbidden functions that enable escape or introspection
    FORBIDDEN_FUNCTIONS = {
        'eval', 'exec', 'compile', '__import__',
        'vars', 'globals', 'locals', 'dir', 'open',
        'input', 'breakpoint', 'help', 'copyright', 'credits', 'license'
    }

    # Forbidden attribute access functions
    FORBIDDEN_ATTR_FUNCTIONS = {'getattr', 'setattr', 'delattr', 'hasattr'}

    def __init__(self, venv_path: str = None, logger=None, enable_hardening: bool = True):
        """
        Args:
            venv_path: Path to Python venv with pvlib installed.
                      If None, uses system Python (not recommended).
            logger: Optional StructuredLogger for observability
            enable_hardening: Enable Phase 1 security hardening (default: True)
        """
        self.venv_path = Path(venv_path) if venv_path else None
        self.logger = logger
        self.enable_hardening = enable_hardening
        self.temp_dir = Path(tempfile.gettempdir()) / "sun-sleuth-code"
        self.temp_dir.mkdir(exist_ok=True)

        if self.venv_path:
            # Determine Python executable path (cross-platform)
            if os.name == 'nt':  # Windows
                # Try venv structure first (Scripts/python.exe)
                venv_exe = self.venv_path / "Scripts" / "python.exe"
                # Fall back to system Python structure (python.exe in root)
                system_exe = self.venv_path / "python.exe"
                if venv_exe.exists():
                    self.python_exe = venv_exe
                elif system_exe.exists():
                    self.python_exe = system_exe
                else:
                    raise FileNotFoundError(f"Python executable not found at {venv_exe} or {system_exe}")
            else:  # Unix-like
                # Try venv structure first (bin/python)
                venv_exe = self.venv_path / "bin" / "python"
                # Fall back to system Python structure (python in root)
                system_exe = self.venv_path / "python"
                if venv_exe.exists():
                    self.python_exe = venv_exe
                elif system_exe.exists():
                    self.python_exe = system_exe
                else:
                    raise FileNotFoundError(f"Python executable not found at {venv_exe} or {system_exe}")
        else:
            # Fall back to current interpreter
            import sys
            self.python_exe = sys.executable

    def check_syntax(self, code: str) -> Optional[str]:
        """
        Check Python syntax without executing.

        Returns:
            None if valid, error message if invalid
        """
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"Syntax error at line {e.lineno}, column {e.offset}: {e.msg}"
        except Exception as e:
            return f"Syntax validation error: {str(e)}"

    def check_imports(self, code: str) -> Optional[str]:
        """
        Validate that all imports are in the allowlist.

        Returns:
            None if all imports allowed, error message if forbidden imports found
        """
        try:
            tree = ast.parse(code)
            forbidden = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        base_module = alias.name.split('.')[0]
                        if base_module not in self.ALLOWED_IMPORTS:
                            forbidden.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        base_module = node.module.split('.')[0]
                        if base_module not in self.ALLOWED_IMPORTS:
                            forbidden.append(node.module)

            if forbidden:
                return (f"Forbidden imports detected: {', '.join(forbidden)}. "
                       f"Allowed modules: {', '.join(sorted(self.ALLOWED_IMPORTS))}")
            return None
        except Exception as e:
            return f"Import validation error: {str(e)}"

    def wrap_with_determinism(self, code: str, seed: int = 42, fixed_timestamp: float = 1704067200.0) -> str:
        """
        Wrap user code with determinism helpers (Phase 1 Hardening).

        Enforces:
        - Fixed random seed (both random and numpy.random)
        - Fixed time.time() return value
        - Fixed datetime.now() return value
        - Predictable execution environment

        Args:
            code: User Python code
            seed: Random seed (default: 42)
            fixed_timestamp: Unix timestamp to return from time.time() (default: 2024-01-01 00:00:00 UTC)

        Returns:
            Wrapped code string
        """
        # Escape quotes in user code for string embedding
        code_escaped = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        wrapper = f'''
# === Determinism Wrapper (Phase 1 Security Hardening) ===
import random
import time as _time_module
import datetime as _datetime_module

# Seed random for reproducibility
random.seed({seed})

# Try to seed numpy.random if it will be imported (check code content)
_has_numpy = 'numpy' in """{code_escaped}""" or 'np.' in """{code_escaped}"""
if _has_numpy:
    try:
        import numpy as np
        np.random.seed({seed})
    except:
        pass

# Mock time.time() to return fixed value
_original_time = _time_module.time
_time_module.time = lambda: {fixed_timestamp}

# Mock datetime.now() by replacing at module level
_original_datetime_class = _datetime_module.datetime
_fixed_datetime = _original_datetime_class.fromtimestamp({fixed_timestamp})

class _DeterministicDatetime(_original_datetime_class):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _fixed_datetime
        return _fixed_datetime.replace(tzinfo=tz)

_datetime_module.datetime = _DeterministicDatetime

# === User Code Below ===
{code}
'''
        return wrapper

    def check_dangerous_patterns(self, code: str) -> Optional[str]:
        """
        Block dangerous Python constructs using AST analysis (Phase 1 Hardening).

        Forbidden patterns:
        - eval(), exec(), compile() calls
        - __import__ usage
        - Access to __code__, __globals__, __builtins__, etc.
        - getattr/setattr/delattr on dunder attributes
        - open() calls (file I/O should be controlled)

        Returns:
            None if safe, error message if dangerous patterns found
        """
        if not self.enable_hardening:
            return None

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                # Block forbidden function calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in self.FORBIDDEN_FUNCTIONS:
                            return f"SECURITY: Forbidden function: {node.func.id}()"

                        # Check getattr/setattr with dunder attribute names
                        if node.func.id in self.FORBIDDEN_ATTR_FUNCTIONS:
                            if len(node.args) >= 2:
                                attr_arg = node.args[1]
                                if isinstance(attr_arg, ast.Constant):
                                    if isinstance(attr_arg.value, str):
                                        if attr_arg.value.startswith('__'):
                                            return f"SECURITY: Forbidden: {node.func.id}() with dunder attribute '{attr_arg.value}'"

                # Block direct reference to dangerous dunder names (e.g., __builtins__)
                if isinstance(node, ast.Name):
                    if node.id.startswith('__') and node.id.endswith('__'):
                        if node.id not in self.SAFE_DUNDERS:
                            return f"SECURITY: Forbidden name reference: {node.id}"

                # Block access to dunder attributes (except safe ones)
                if isinstance(node, ast.Attribute):
                    if node.attr.startswith('__') and node.attr.endswith('__'):
                        if node.attr not in self.SAFE_DUNDERS:
                            return f"SECURITY: Forbidden attribute access: {node.attr}"

            return None
        except Exception as e:
            return f"Security pattern validation error: {str(e)}"

    def _apply_resource_limits(self):
        """
        Apply resource limits before executing code (Phase 1 Hardening).
        Only works on Unix-like systems.

        Limits:
        - CPU time: 30 seconds
        - Memory: 512 MB
        - File size: 10 MB
        - Max processes: 1 (prevent fork bombs)
        """
        if not RESOURCE_AVAILABLE or not self.enable_hardening:
            return

        # CPU time limit: 30 seconds
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))

        # Memory limit: 512 MB
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

        # File size limit: 10 MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))

        # Max 1 process (prevent fork bombs)
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))

    def execute(
        self,
        code: str,
        timeout: int = 60,
        capture_stdout: bool = True,
        max_output_bytes: int = 1_000_000
    ) -> Tuple[bool, str, str]:
        """
        Execute Python code in isolated environment.

        Args:
            code: Python code string to execute
            timeout: Max execution time in seconds
            capture_stdout: Whether to capture and return stdout
            max_output_bytes: Maximum output size in bytes (default: 1 MB)

        Returns:
            (success: bool, stdout: str, stderr: str)
        """
        # Write code to temporary file with UTF-8 encoding
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name

        try:
            # Run code in subprocess with resource limits
            result = subprocess.run(
                [str(self.python_exe), temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd(),
                preexec_fn=self._apply_resource_limits if RESOURCE_AVAILABLE and os.name != 'nt' else None
            )

            success = result.returncode == 0
            stdout = result.stdout if capture_stdout else ""
            stderr = result.stderr

            # Apply output size limits (Phase 1 Hardening)
            if self.enable_hardening and len(stdout) > max_output_bytes:
                stdout = stdout[:max_output_bytes]
                stderr += f"\n[SECURITY] Output truncated (exceeded {max_output_bytes} bytes limit)"

            if self.enable_hardening and len(stderr) > max_output_bytes:
                stderr = stderr[:max_output_bytes]

            return success, stdout, stderr

        except subprocess.TimeoutExpired:
            return False, "", f"Execution timed out after {timeout} seconds"
        except Exception as e:
            return False, "", f"Execution error: {str(e)}"
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except:
                pass

    def execute_with_json_output(self, code: str, timeout: int = 60, enforce_determinism: bool = False) -> Dict:
        """
        Execute code and parse JSON from stdout.
        Includes syntax and import preflight checks.

        Expected code pattern:
            import json
            result = {"daily_kwh": 42.5, "peak_ac_w": 9850}
            print(json.dumps(result))

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            enforce_determinism: Wrap code with determinism helpers (fixed seed, time)

        Returns:
            {"success": bool, "output": dict|str, "error": str|None, "preflight_failed": bool}
        """
        start_time = time.time()

        # Apply determinism wrapper if requested
        if enforce_determinism and self.enable_hardening:
            code = self.wrap_with_determinism(code)

        # Save code artifact for debugging
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:8]
        code_file = self.temp_dir / f"code_{code_hash}.py"
        code_file.write_text(code, encoding='utf-8')

        # Log tool call start
        if self.logger:
            self.logger.log_event(
                agent="executor",
                event_type="tool_call_start",
                step_name="code_execution",
                data={
                    "code_ref": str(code_file),
                    "code_hash": code_hash,
                    "code_lines": len(code.split('\n')),
                    "timeout": timeout
                }
            )

        # Preflight checks
        syntax_error = self.check_syntax(code)
        if syntax_error:
            error_result = {
                "success": False,
                "output": "",
                "error": f"SYNTAX_ERROR: {syntax_error}\n\nHINT: Fix syntax before execution",
                "preflight_failed": True,
                "exit_code": None
            }
            if self.logger:
                self.logger.log_tool_call(
                    tool="python",
                    input_data={"code_hash": code_hash},
                    result=error_result,
                    error_type="syntax_error",
                    duration_ms=(time.time() - start_time) * 1000
                )
            return error_result

        import_error = self.check_imports(code)
        if import_error:
            error_result = {
                "success": False,
                "output": "",
                "error": f"IMPORT_ERROR: {import_error}\n\nHINT: Use only allowed PV simulation libraries",
                "preflight_failed": True,
                "exit_code": None
            }
            if self.logger:
                self.logger.log_tool_call(
                    tool="python",
                    input_data={"code_hash": code_hash},
                    result=error_result,
                    error_type="import_error",
                    duration_ms=(time.time() - start_time) * 1000
                )
            return error_result

        # Security pattern checks (Phase 1 Hardening)
        if self.enable_hardening:
            security_error = self.check_dangerous_patterns(code)
            if security_error:
                error_result = {
                    "success": False,
                    "output": "",
                    "error": f"{security_error}\n\nHINT: Avoid introspection and dangerous operations",
                    "preflight_failed": True,
                    "exit_code": None
                }
                if self.logger:
                    self.logger.log_tool_call(
                        tool="python",
                        input_data={"code_hash": code_hash},
                        result=error_result,
                        error_type="security_error",
                        duration_ms=(time.time() - start_time) * 1000
                    )
                return error_result

        # Execute code
        success, stdout, stderr = self.execute(code, timeout)
        duration_ms = (time.time() - start_time) * 1000

        if not success:
            # Categorize error type
            error_type = self._categorize_error(stderr)

            # Return both stdout and stderr for better debugging
            result = {
                "success": False,
                "output": stdout,
                "error": stderr,
                "stdout": stdout,
                "stderr": stderr,
                "preflight_failed": False,
                "exit_code": 1  # Non-zero exit indicates runtime error
            }

            if self.logger:
                self.logger.log_tool_call(
                    tool="python",
                    input_data={"code_hash": code_hash},
                    result=result,
                    error_type=error_type,
                    duration_ms=duration_ms
                )

            return result

        # Try to parse last line as JSON
        try:
            lines = stdout.strip().split('\n')
            # Look for JSON in output (usually last line)
            for line in reversed(lines):
                line = line.strip()
                if line.startswith('{') or line.startswith('['):
                    parsed = json.loads(line)
                    result = {
                        "success": True,
                        "output": parsed,
                        "error": None,
                        "raw_stdout": stdout
                    }

                    if self.logger:
                        self.logger.log_tool_call(
                            tool="python",
                            input_data={"code_hash": code_hash},
                            result=result,
                            error_type=None,
                            duration_ms=duration_ms
                        )

                    return result

            # No JSON found, return raw stdout
            result = {
                "success": True,
                "output": stdout,
                "error": None
            }

            if self.logger:
                self.logger.log_tool_call(
                    tool="python",
                    input_data={"code_hash": code_hash},
                    result=result,
                    error_type="schema_error",  # No JSON output
                    duration_ms=duration_ms
                )

            return result

        except json.JSONDecodeError as e:
            result = {
                "success": True,  # Code ran successfully
                "output": stdout,
                "error": f"Could not parse JSON output: {e}"
            }

            if self.logger:
                self.logger.log_tool_call(
                    tool="python",
                    input_data={"code_hash": code_hash},
                    result=result,
                    error_type="json_parse_error",
                    duration_ms=duration_ms
                )

            return result

    def _categorize_error(self, error_msg: str) -> str:
        """
        Categorize error for pattern detection and analytics.

        Args:
            error_msg: Error message from stderr

        Returns:
            Error category string
        """
        error_lower = error_msg.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        elif "modulenotfounderror" in error_lower or "importerror" in error_lower:
            return "import_error"
        elif "keyerror" in error_lower:
            return "key_error"
        elif "attributeerror" in error_lower:
            return "attribute_error"
        elif "valueerror" in error_lower:
            return "value_error"
        elif "typeerror" in error_lower:
            return "type_error"
        elif "nameerror" in error_lower:
            return "name_error"
        elif "zerodivisionerror" in error_lower:
            return "zero_division"
        elif "indexerror" in error_lower:
            return "index_error"
        elif "unexpected keyword" in error_lower or "missing" in error_lower and "argument" in error_lower:
            return "api_parameter_error"
        else:
            return "execution_error"

    def test_environment(self) -> bool:
        """Test that Python environment has required dependencies."""
        test_code = """
import sys
try:
    import pvlib
    import numpy
    import pandas
    import scipy
    print(f"OK: pvlib {pvlib.__version__}")
except ImportError as e:
    print(f"MISSING: {e}")
    sys.exit(1)
"""
        success, stdout, stderr = self.execute(test_code, timeout=10)

        if success:
            print(f"Environment test passed: {stdout.strip()}")
        else:
            print(f"Environment test failed:\n{stderr}")

        return success
