"""
Sun Sleuth - AI Agent for Solar PV Simulation

Main agent package.
"""

from .multi_agent_cli import MultiAgentPV
from .executor import PythonExecutor

__version__ = "0.3.0"

__all__ = ["MultiAgentPV", "PythonExecutor"]
