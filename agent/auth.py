#!/usr/bin/env python3
"""
Authentication management for Helio.
Handles OpenRouter API key storage securely using OS keychain.
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
    import keyring
    from keyring.errors import KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Configuration
SERVICE_NAME = "helio-pv-cli"
KEY_NAME = "openrouter-api-key"
CONFIG_DIR = Path.home() / ".config" / "helio"
CONFIG_FILE = CONFIG_DIR / "config"


def get_api_key() -> Optional[str]:
    """
    Get OpenRouter API key from (in order):
    1. OPENROUTER_API_KEY environment variable
    2. OS keychain (macOS Keychain / Windows Credential Manager / Linux Secret Service)
    3. Config file (fallback, with 0600 permissions)

    Returns:
        API key if found, None otherwise
    """
    # 1. Check environment variable first
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()

    # 2. Try OS keychain
    if KEYRING_AVAILABLE:
        try:
            key = keyring.get_password(SERVICE_NAME, KEY_NAME)
            if key:
                return key.strip()
        except KeyringError:
            pass  # Keychain not available, try config file

    # 3. Try config file (fallback)
    if CONFIG_FILE.exists():
        try:
            key = CONFIG_FILE.read_text().strip()
            if key:
                return key
        except (IOError, PermissionError):
            pass

    return None


def store_api_key(key: str) -> tuple[bool, str]:
    """
    Store API key securely.

    Tries (in order):
    1. OS keychain (preferred)
    2. Config file with 0600 permissions (fallback)

    Args:
        key: OpenRouter API key (starts with sk-or-...)

    Returns:
        (success: bool, storage_location: str)
    """
    key = key.strip()

    # Validate key format
    if not key.startswith("sk-or-"):
        return False, "Invalid key format (should start with sk-or-)"

    # Try OS keychain first (preferred)
    if KEYRING_AVAILABLE:
        try:
            keyring.set_password(SERVICE_NAME, KEY_NAME, key)
            backend = keyring.get_keyring()
            backend_name = type(backend).__name__
            return True, f"OS keychain ({backend_name})"
        except KeyringError as e:
            # Keychain failed, fall back to config file
            pass

    # Fallback: config file with restrictive permissions
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        CONFIG_FILE.write_text(key)

        # Set restrictive permissions (owner read/write only)
        if sys.platform != "win32":
            os.chmod(CONFIG_FILE, 0o600)

        return True, f"Config file ({CONFIG_FILE})"
    except (IOError, PermissionError) as e:
        return False, f"Storage failed: {e}"


def delete_api_key() -> tuple[bool, str]:
    """
    Delete stored API key from all locations.

    Returns:
        (success: bool, message: str)
    """
    deleted_from = []

    # Try keychain
    if KEYRING_AVAILABLE:
        try:
            keyring.delete_password(SERVICE_NAME, KEY_NAME)
            deleted_from.append("keychain")
        except KeyringError:
            pass  # Not found or not available

    # Try config file
    if CONFIG_FILE.exists():
        try:
            CONFIG_FILE.unlink()
            deleted_from.append("config file")
        except (IOError, PermissionError):
            pass

    if deleted_from:
        return True, f"Deleted from: {', '.join(deleted_from)}"
    else:
        return False, "No stored API key found"


def get_storage_location() -> Optional[str]:
    """
    Determine where the API key is stored (without revealing the key).

    Returns:
        Storage location string, or None if not found
    """
    # Check environment
    if os.environ.get("OPENROUTER_API_KEY"):
        return "environment variable (OPENROUTER_API_KEY)"

    # Check keychain
    if KEYRING_AVAILABLE:
        try:
            if keyring.get_password(SERVICE_NAME, KEY_NAME):
                backend = keyring.get_keyring()
                backend_name = type(backend).__name__
                return f"OS keychain ({backend_name})"
        except KeyringError:
            pass

    # Check config file
    if CONFIG_FILE.exists() and CONFIG_FILE.read_text().strip():
        return f"config file ({CONFIG_FILE})"

    return None


def is_interactive() -> bool:
    """Check if running in an interactive terminal (TTY)."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def prompt_for_key() -> Optional[str]:
    """
    Interactively prompt for API key (masked input).

    Returns:
        API key if provided, None if cancelled
    """
    import getpass

    print("\n" + "=" * 60)
    print("OpenRouter API Key Required")
    print("=" * 60)
    print("\nHelio uses OpenRouter to access AI models.")
    print("\nGet your API key at: https://openrouter.ai/keys")
    print("(Tip: You can set a credit limit on the key for safety)")
    print("\nWe'll store it securely in your system keychain.")
    print("You can revoke/rotate it anytime with: helio auth logout")
    print("\n" + "=" * 60)

    try:
        key = getpass.getpass("Enter your OpenRouter API key (or Ctrl+C to cancel): ")
        return key.strip() if key else None
    except (KeyboardInterrupt, EOFError):
        print("\n\nCancelled.")
        return None


def interactive_login() -> bool:
    """
    Interactive login flow.

    Returns:
        True if successful, False otherwise
    """
    key = prompt_for_key()

    if not key:
        return False

    success, location = store_api_key(key)

    if success:
        print(f"\n✓ API key stored securely in: {location}")
        print("\nYou're all set! Run 'helio' to start.")
        return True
    else:
        print(f"\n✗ Failed to store API key: {location}")
        return False


def show_status():
    """Show authentication status (without revealing the key)."""
    location = get_storage_location()

    print("\n" + "=" * 60)
    print("Helio Authentication Status")
    print("=" * 60)

    if location:
        print(f"\n✓ API key found in: {location}")
        print("\nTo revoke: helio auth logout")
        print("To update: helio auth login (will overwrite)")
    else:
        print("\n✗ No API key found")
        print("\nTo set up: helio auth login")
        print("Or set environment variable: OPENROUTER_API_KEY=sk-or-...")

    print("=" * 60 + "\n")
