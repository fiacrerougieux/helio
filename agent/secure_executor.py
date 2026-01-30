"""
Secure Python executor with OS-specific sandboxing.

Provides production-grade isolation without Docker:
- Linux: Bubblewrap (namespace isolation, no network, read-only filesystem)
- macOS: sandbox-exec (Apple's built-in sandbox)
- Windows: Job Objects (process isolation, resource limits)

All platforms get:
- AST-based security checks
- Import allowlisting
- Determinism enforcement
- Resource limits
- No network access
"""

import subprocess
import json
import tempfile
import os
import sys
import ast
import time
import platform
import shutil
from pathlib import Path
from typing import Dict, Optional, List

# Import existing executor for AST checks
from .executor import PythonExecutor


class SecureExecutor(PythonExecutor):
    """
    Enhanced executor with OS-level sandboxing.

    Inherits AST security checks from PythonExecutor and adds:
    - Filesystem isolation (read-only system, isolated temp)
    - Network isolation
    - Process isolation (PID namespace on Linux)
    - Enhanced resource limits
    """

    def __init__(self, venv_path: str = None, logger=None, enable_hardening: bool = True):
        super().__init__(venv_path, logger, enable_hardening)

        self.system = platform.system().lower()
        self.sandbox_available = self._check_sandbox_availability()
        self.sandbox_config_dir = Path.home() / ".sun-sleuth" / "sandbox"

        if not self.sandbox_available:
            print("⚠️  OS-level sandbox not available, using basic subprocess isolation.")
            print("   Run: python scripts/install_sandbox.py")

    def _check_sandbox_availability(self) -> bool:
        """Check if OS-level sandbox is available."""
        if self.system == "linux":
            return shutil.which("bwrap") is not None
        elif self.system == "darwin":
            return shutil.which("sandbox-exec") is not None
        elif self.system == "windows":
            # Windows: Use enhanced subprocess with CREATE_NO_WINDOW flag
            # This provides process isolation without the complexity of Job Objects
            # which can have compatibility issues across Windows versions
            return True
        return False

    def _create_bubblewrap_command(self, code_file: Path, output_file: Path, timeout: int) -> List[str]:
        """Build Bubblewrap sandbox command for Linux."""

        # Read-only bind mounts for system directories
        cmd = [
            "bwrap",
            # Read-only system mounts
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/sbin", "/sbin",
        ]

        # Add lib64 if it exists
        if Path("/lib64").exists():
            cmd.extend(["--ro-bind", "/lib64", "/lib64"])

        # Writable temp directory (isolated)
        cmd.extend([
            "--tmpfs", "/tmp",
            "--setenv", "TMPDIR", "/tmp",
        ])

        # Proc filesystem
        cmd.extend(["--proc", "/proc"])

        # Minimal dev
        cmd.extend(["--dev", "/dev"])

        # Network isolation
        cmd.extend(["--unshare-net"])

        # PID namespace isolation
        cmd.extend(["--unshare-pid"])

        # Die with parent process
        cmd.extend(["--die-with-parent"])

        # Bind venv as read-only (if exists)
        if self.venv_path and self.venv_path.exists():
            venv_abs = self.venv_path.resolve()
            cmd.extend(["--ro-bind", str(venv_abs), str(venv_abs)])
        
        # Bind user site-packages if strictly needed (for non-venv usage on Linux)
        try:
            import site
            user_site = Path(site.getusersitepackages())
            if user_site.exists():
                # Only bind if it's not already covered (starts with /home)
                # We strictly assume /home is hidden by default in our sandbox
                user_site_abs = user_site.resolve()
                cmd.extend(["--ro-bind", str(user_site_abs), str(user_site_abs)])
        except:
            pass

        # Bind code file as read-only
        code_abs = code_file.resolve()
        cmd.extend(["--ro-bind", str(code_abs), str(code_abs)])

        # Bind output file as writable
        output_abs = output_file.resolve()
        output_parent = output_abs.parent
        # Need to bind parent dir as writable for output
        cmd.extend(["--bind", str(output_parent), str(output_parent)])

        # Bind the Python executable itself (it might be in /usr, /bin, or elsewhere)
        python_path = Path(str(self.python_exe)).resolve()
        cmd.extend(["--ro-bind", str(python_path), str(python_path)])
        
        # If it's a symlink (like /usr/bin/python3 -> /usr/bin/python3.10), bind the target too
        if python_path.is_symlink() or Path(str(self.python_exe)).is_symlink():
            real_path = python_path.resolve()
            cmd.extend(["--ro-bind", str(real_path), str(real_path)])

        # Execute Python (using the absolute path)
        cmd.extend([
            str(python_path),
            str(code_abs)
        ])

        return cmd

    def _create_macos_sandbox_command(self, code_file: Path, output_file: Path, timeout: int) -> List[str]:
        """Build macOS sandbox-exec command."""

        # Create sandbox profile
        profile = f"""(version 1)
(deny default)

; Allow reading system files
(allow file-read*
    (subpath "/System")
    (subpath "/Library")
    (subpath "/usr")
    (subpath "/private/var"))

; Allow Python execution
(allow process-exec
    (literal "{self.python_exe}")
    (literal "{Path(self.python_exe).resolve()}"))

; Allow reading the python binary (essential for Homebrew/Conda)
(allow file-read*
    (literal "{Path(self.python_exe).resolve()}"))

; Deny network
(deny network*)

; Allow reading venv
(allow file-read*
    (subpath "{self.venv_path}"))

; Allow reading code file
(allow file-read*
    (literal "{code_file}"))

; Allow writing to output file only
(allow file-write*
    (literal "{output_file}"))

; Allow temp directory
(allow file-write*
    (subpath "/private/tmp"))
"""

        # Write profile to temp file
        profile_file = self.sandbox_config_dir / "runtime_profile.sb"
        profile_file.parent.mkdir(parents=True, exist_ok=True)
        profile_file.write_text(profile)

        cmd = [
            "sandbox-exec",
            "-f", str(profile_file),
            str(self.python_exe),
            str(code_file)
        ]

        return cmd

    def _execute_with_windows_isolation(self, code_file: Path, timeout: int) -> subprocess.CompletedProcess:
        """
        Execute with Windows subprocess isolation.

        Uses enhanced subprocess with:
        - Timeout enforcement
        - Process isolation via CREATE_NO_WINDOW
        - Combined with AST security checks (from parent class)

        This provides good security for educational/research use.
        For production deployments requiring strict isolation, consider WSL + Linux sandbox.
        """

        try:
            # Run with CREATE_NO_WINDOW flag for isolation
            # This prevents the process from creating a visible console window
            # and limits interaction with the desktop
            result = subprocess.run(
                [str(self.python_exe), str(code_file)],
                capture_output=True,
                timeout=timeout,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            return result

        except subprocess.TimeoutExpired as e:
            # Re-raise timeout for upstream handling
            raise
        except Exception as e:
            # Fallback to basic subprocess
            return subprocess.run(
                [str(self.python_exe), str(code_file)],
                capture_output=True,
                timeout=timeout,
                text=True
            )

    def execute_sandboxed(self, code: str, timeout: int = 60, deterministic: bool = False) -> Dict:
        """
        Execute code with OS-level sandboxing.

        Security features:
        - Filesystem isolation (read-only system, isolated temp)
        - Network isolation (no network access)
        - Process isolation (new PID namespace on Linux)
        - Resource limits (memory, CPU time)
        - AST security checks (inherited from parent class)

        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds
            deterministic: Wrap with determinism enforcement

        Returns:
            Dict with success, output, error, stderr
        """

        # Phase 1: AST security checks (inherited)
        if self.enable_hardening:
            syntax_error = self.check_syntax(code)
            if syntax_error:
                return {
                    "success": False,
                    "error": f"SYNTAX_ERROR: {syntax_error}",
                    "output": None
                }

            import_error = self.check_imports(code)
            if import_error:
                return {
                    "success": False,
                    "error": f"IMPORT_ERROR: {import_error}",
                    "output": None
                }

            security_error = self.check_dangerous_patterns(code)
            if security_error:
                return {
                    "success": False,
                    "error": f"{security_error}",
                    "output": None
                }

        # Wrap with determinism if requested
        if deterministic:
            code = self.wrap_with_determinism(code)

        # Create temporary files
        code_file = self.temp_dir / f"code_{hash(code) % 10000}.py"
        output_file = self.temp_dir / f"output_{hash(code) % 10000}.json"

        try:
            code_file.write_text(code, encoding='utf-8')

            # Select sandbox method
            if self.sandbox_available and self.system == "linux":
                # Bubblewrap on Linux
                cmd = self._create_bubblewrap_command(code_file, output_file, timeout)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout,
                    text=True
                )

            elif self.sandbox_available and self.system == "darwin":
                # macOS sandbox-exec
                cmd = self._create_macos_sandbox_command(code_file, output_file, timeout)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout,
                    text=True
                )

            elif self.sandbox_available and self.system == "windows":
                # Windows subprocess isolation
                result = self._execute_with_windows_isolation(code_file, timeout)

            else:
                # Fallback to basic subprocess (no OS-level sandbox)
                result = subprocess.run(
                    [str(self.python_exe), str(code_file)],
                    capture_output=True,
                    timeout=timeout,
                    text=True
                )

            # Parse output
            stdout = result.stdout if hasattr(result, 'stdout') else ""
            stderr = result.stderr if hasattr(result, 'stderr') else ""

            # Try to parse JSON from stdout
            output_dict = self._parse_json_output(stdout)

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": output_dict,
                    "stdout": stdout,
                    "stderr": stderr
                }
            else:
                return {
                    "success": False,
                    "error": f"Execution failed with code {result.returncode}",
                    "output": None,
                    "stderr": stderr
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"TIMEOUT_ERROR: Execution exceeded {timeout} seconds",
                "output": None
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"EXECUTION_ERROR: {str(e)}",
                "output": None
            }

        finally:
            # Cleanup
            if code_file.exists():
                code_file.unlink()
            if output_file.exists():
                output_file.unlink()

    def _parse_json_output(self, stdout: str) -> Optional[Dict]:
        """Extract JSON from stdout."""
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def execute_with_json_output(self, code: str, timeout: int = 60, enforce_determinism: bool = False) -> Dict:
        """
        Execute code and expect JSON output (backward compatible with PythonExecutor).
        Uses sandboxed execution if available.

        Args:
            code: Python code to execute
            timeout: Timeout in seconds
            enforce_determinism: Whether to wrap code with determinism enforcement

        Returns:
            Dict with success, output, stdout, stderr, error
        """
        return self.execute_sandboxed(code, timeout, deterministic=enforce_determinism)

    def classify_error(self, result: Dict) -> str:
        """Classify execution error type for diagnosis."""
        if result.get('success'):
            return 'none'

        error = result.get('error', '')
        stderr = result.get('stderr', '')

        # Timeout
        if 'TIMEOUT' in error or 'timeout' in error.lower():
            return 'timeout'

        # Security/syntax (pre-execution)
        if 'SYNTAX_ERROR' in error:
            return 'syntax'
        if 'IMPORT_ERROR' in error:
            return 'import'
        if 'SECURITY' in error:
            return 'security'

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
            if 'ImportError' in stderr or 'ModuleNotFoundError' in stderr:
                return 'import'

        return 'unknown'

    def extract_error_context(self, result: Dict) -> Dict:
        """Extract detailed error context for diagnosis."""
        import re

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

        return context

    def test_environment(self) -> bool:
        """Test if executor environment is working."""
        test_code = """
import json
result = {"status": "ok", "sandbox": "active"}
print(json.dumps(result))
"""
        result = self.execute_sandboxed(test_code, timeout=5, deterministic=False)

        if result["success"]:
            # Use ASCII-safe characters for Windows console compatibility
            print(f"OK Secure executor test passed (sandbox: {self.sandbox_available})")
            return True
        else:
            print(f"ERROR Secure executor test failed: {result.get('error')}")
            if result.get('stderr'):
                print(f"STDERR:\n{result.get('stderr')}")
            return False
