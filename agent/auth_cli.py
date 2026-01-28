#!/usr/bin/env python3
"""
CLI interface for Helio authentication management.
Handles: helio auth login/logout/status
"""

import sys
import argparse
from . import auth


def main():
    """Entry point for helio auth subcommand."""
    parser = argparse.ArgumentParser(
        prog="helio auth",
        description="Manage OpenRouter API authentication"
    )

    subparsers = parser.add_subparsers(dest="command", help="Authentication command")

    # helio auth login
    login_parser = subparsers.add_parser(
        "login",
        help="Interactively set up OpenRouter API key"
    )

    # helio auth logout
    logout_parser = subparsers.add_parser(
        "logout",
        help="Delete stored API key"
    )

    # helio auth status
    status_parser = subparsers.add_parser(
        "status",
        help="Show where API key is stored (without revealing it)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "login":
        success = auth.interactive_login()
        return 0 if success else 1

    elif args.command == "logout":
        success, message = auth.delete_api_key()
        print("\n" + "=" * 60)
        print("Helio Logout")
        print("=" * 60)
        if success:
            print(f"\n✓ {message}")
        else:
            print(f"\n✗ {message}")
        print("=" * 60 + "\n")
        return 0 if success else 1

    elif args.command == "status":
        auth.show_status()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
