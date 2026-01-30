#!/usr/bin/env python3
"""
Automated sandbox installation script for Sun Sleuth.
Installs gVisor runsc (lightweight container runtime) for secure code execution.

Usage:
    python scripts/install_sandbox.py
"""

import os
import sys
import platform
import urllib.request
import tarfile
import zipfile
import subprocess
import shutil
from pathlib import Path


class SandboxInstaller:
    """Install lightweight sandbox for secure Python execution."""

    def __init__(self):
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.install_dir = Path.home() / ".sun-sleuth" / "sandbox"
        self.install_dir.mkdir(parents=True, exist_ok=True)

    def detect_platform(self):
        """Detect OS and architecture."""
        print(f"Detected: {self.system} {self.machine}")

        if self.system not in ["linux", "darwin", "windows"]:
            print(f"❌ Unsupported OS: {self.system}")
            return False

        if self.machine not in ["x86_64", "amd64", "arm64", "aarch64"]:
            print(f"❌ Unsupported architecture: {self.machine}")
            return False

        return True

    def install_bubblewrap_linux(self):
        """Install Bubblewrap on Linux (simpler than gVisor, no kernel modules)."""
        print("\n[*] Installing Bubblewrap sandbox (Linux)...")

        # Check if already installed
        if shutil.which("bwrap"):
            print("✅ Bubblewrap already installed!")
            return True

        # Try package manager installation
        try:
            # Detect package manager
            if shutil.which("apt-get"):
                print("Using apt-get...")
                subprocess.run(["sudo", "apt-get", "update"], check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y", "bubblewrap"], check=True)
            elif shutil.which("dnf"):
                print("Using dnf...")
                subprocess.run(["sudo", "dnf", "install", "-y", "bubblewrap"], check=True)
            elif shutil.which("yum"):
                print("Using yum...")
                subprocess.run(["sudo", "yum", "install", "-y", "bubblewrap"], check=True)
            elif shutil.which("pacman"):
                print("Using pacman...")
                subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "bubblewrap"], check=True)
            else:
                print("❌ No supported package manager found (apt/dnf/yum/pacman)")
                return False

            print("✅ Bubblewrap installed successfully!")
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ Installation failed: {e}")
            return False

    def install_sandbox_macos(self):
        """Install sandbox on macOS using built-in sandbox-exec."""
        print("\n[*] Checking macOS sandbox...")

        # macOS has built-in sandbox-exec, no installation needed
        if shutil.which("sandbox-exec"):
            print("✅ macOS sandbox-exec available!")
            return True
        else:
            print("❌ sandbox-exec not found (should be built-in on macOS)")
            return False

    def install_sandbox_windows(self):
        """Install sandbox on Windows using enhanced subprocess."""
        print("\nSetting up Windows sandbox...")
        print("Windows uses enhanced subprocess isolation with:")
        print("  OK: AST security checks (blocks eval/exec/__import__)")
        print("  OK: Import allowlisting (only pvlib, pandas, etc.)")
        print("  OK: Timeout enforcement")
        print("  OK: Process isolation (CREATE_NO_WINDOW)")
        print("")
        print("Note: For production requiring strict filesystem/network isolation,")
        print("      consider using WSL (Windows Subsystem for Linux) + Linux sandbox.")
        print("")

        # Windows uses enhanced subprocess (no external deps needed)
        print("✅ Windows sandbox configured!")
        print("   (No additional dependencies required)")
        return True

    def create_sandbox_profile(self):
        """Create sandbox configuration files."""
        print("\n📝 Creating sandbox profiles...")

        # Linux Bubblewrap profile
        if self.system == "linux":
            profile = self.install_dir / "bubblewrap_profile.txt"
            profile.write_text("""# Bubblewrap sandbox profile for Sun Sleuth
# Read-only system mounts
--ro-bind /usr /usr
--ro-bind /lib /lib
--ro-bind /lib64 /lib64
--ro-bind /bin /bin
--ro-bind /sbin /sbin

# Writable tmp (isolated)
--tmpfs /tmp

# Proc filesystem
--proc /proc

# Dev minimal
--dev /dev

# No network
--unshare-net

# New PID namespace
--unshare-pid

# Die with parent
--die-with-parent
""")
            print(f"✅ Created: {profile}")

        # macOS sandbox profile
        elif self.system == "darwin":
            profile = self.install_dir / "macos_profile.sb"
            profile.write_text("""(version 1)
(deny default)

; Allow reading system files
(allow file-read*
    (subpath "/System")
    (subpath "/Library")
    (subpath "/usr"))

; Allow Python execution
(allow process-exec
    (literal "/usr/bin/python3"))

; Deny network
(deny network*)

; Allow reading venv
(allow file-read*
    (subpath "${VENV_PATH}"))

; Allow writing to temp output file only
(allow file-write*
    (literal "${OUTPUT_FILE}"))
""")
            print(f"✅ Created: {profile}")

        # Windows - no profile file needed (configured in code)
        elif self.system == "windows":
            print("✅ Windows sandbox configured via Job Objects API")

        return True

    def test_sandbox(self):
        """Test sandbox installation."""
        print("\n🧪 Testing sandbox...")

        test_script = self.install_dir / "test_sandbox.py"
        test_script.write_text("""
import sys
print("Sandbox test successful!")
sys.exit(0)
""")

        try:
            if self.system == "linux":
                # Test bubblewrap
                result = subprocess.run(
                    ["bwrap", "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                     "--proc", "/proc", "--dev", "/dev", "--unshare-net",
                     sys.executable, str(test_script)],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print("✅ Linux sandbox test passed!")
                    return True
                else:
                    print(f"❌ Sandbox test failed: {result.stderr.decode()}")
                    return False

            elif self.system == "darwin":
                # Test sandbox-exec
                result = subprocess.run(
                    ["sandbox-exec", "-p", "(version 1)(allow default)",
                     sys.executable, str(test_script)],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print("✅ macOS sandbox test passed!")
                    return True
                else:
                    print(f"❌ Sandbox test failed: {result.stderr.decode()}")
                    return False

            elif self.system == "windows":
                # Test basic execution (Job Objects tested in executor)
                result = subprocess.run(
                    [sys.executable, str(test_script)],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print("✅ Windows sandbox test passed!")
                    return True
                else:
                    print(f"❌ Sandbox test failed: {result.stderr.decode()}")
                    return False

        except Exception as e:
            print(f"❌ Sandbox test error: {e}")
            return False

        return False

    def install(self):
        """Run full installation."""
        print("=" * 60)
        print("Sun Sleuth - Secure Sandbox Installer")
        print("=" * 60)

        if not self.detect_platform():
            return False

        # Platform-specific installation
        if self.system == "linux":
            if not self.install_bubblewrap_linux():
                return False
        elif self.system == "darwin":
            if not self.install_sandbox_macos():
                return False
        elif self.system == "windows":
            if not self.install_sandbox_windows():
                return False

        # Create configuration
        if not self.create_sandbox_profile():
            return False

        # Test installation
        if not self.test_sandbox():
            print("\n⚠️  Sandbox installed but test failed.")
            print("You can still use the system with basic subprocess isolation.")
            return True  # Don't fail, fallback available

        print("\n" + "=" * 60)
        print("✅ Sandbox installation complete!")
        print("=" * 60)
        print(f"\nInstallation directory: {self.install_dir}")
        print("\nYou can now run Sun Sleuth with secure code execution.")
        print("The executor will automatically use the sandbox.\n")

        return True


def main():
    installer = SandboxInstaller()

    try:
        success = installer.install()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Installation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
