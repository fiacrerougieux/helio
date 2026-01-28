"""
Structured JSON logging for multi-agent system observability.

Implements best practices from observability guidelines:
- JSON Lines format for machine-readable logs
- Session/trace IDs for correlation
- Semantic step labels
- Agent decision reasoning capture
- Tool execution instrumentation
"""

import json
import time
import hashlib
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime


class StructuredLogger:
    """
    Structured logger for multi-agent system events.

    Logs events in JSON Lines format with consistent schema:
    - timestamp: when the event happened
    - session_id: unique ID tying all events in one conversation
    - agent: which agent logged the event
    - event_type: type of event (decision, tool_call, etc.)
    - step_name: semantic label for the step
    - duration_ms: optional timing information
    - data: event-specific fields
    """

    def __init__(self, session_id: str, log_file: Optional[Path] = None, debug: bool = False):
        """
        Initialize structured logger.

        Args:
            session_id: Unique session identifier
            log_file: Optional file path for JSON Lines output
            debug: If True, also print events to console
        """
        self.session_id = session_id
        self.log_file = log_file
        self.debug = debug
        self.session_start = time.time()

        # Create log file parent directory if needed
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_event(
        self,
        agent: str,
        event_type: str,
        step_name: str,
        data: Dict[str, Any],
        duration_ms: Optional[float] = None
    ):
        """
        Log a structured event.

        Args:
            agent: Agent name (Router, SimAgent, QAAgent, Planner, executor)
            event_type: Event type (decision, tool_call_start, tool_call_end, error, etc.)
            step_name: Semantic step label (routing, code_generation, code_execution, qa_validation)
            data: Event-specific data fields
            duration_ms: Optional duration in milliseconds
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": round(time.time() - self.session_start, 3),
            "session_id": self.session_id,
            "agent": agent,
            "event_type": event_type,
            "step_name": step_name,
            "duration_ms": round(duration_ms, 1) if duration_ms else None,
            **data
        }

        # Write to log file
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

        # Print to console if debug mode
        if self.debug:
            print(f"[LOG] {agent}.{event_type}: {step_name}")
            if duration_ms:
                print(f"      Duration: {duration_ms:.1f}ms")
            for key, val in data.items():
                if key not in ["code", "output"]:  # Don't spam full code/output
                    print(f"      {key}: {val}")

    def log_decision(
        self,
        agent: str,
        decision: str,
        reasoning: str,
        step_name: str = "agent_decision",
        confidence: Optional[float] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Log an agent decision with reasoning.

        Args:
            agent: Agent name
            decision: The decision made (e.g., "route=simulate", "verdict=ok")
            reasoning: Why this decision was made
            step_name: Semantic step label
            confidence: Optional confidence score
            metadata: Additional decision context
        """
        data = {
            "decision": decision,
            "reasoning": reasoning,
            "confidence": confidence
        }
        if metadata:
            data.update(metadata)

        self.log_event(
            agent=agent,
            event_type="decision",
            step_name=step_name,
            data=data
        )

    def log_tool_call(
        self,
        tool: str,
        input_data: Dict,
        result: Optional[Dict] = None,
        error_type: Optional[str] = None,
        duration_ms: float = 0,
        step_name: str = "tool_execution"
    ):
        """
        Log a tool invocation and result.

        Args:
            tool: Tool name (python, pvlib, etc.)
            input_data: Tool inputs (code hash, parameters, etc.)
            result: Tool output or None if call incomplete
            error_type: Error category if failed
            duration_ms: Execution duration
            step_name: Semantic step label
        """
        # Hash large inputs to avoid log bloat
        processed_input = {}
        for key, val in input_data.items():
            if key == "code" and isinstance(val, str) and len(val) > 200:
                processed_input["code_hash"] = hashlib.sha256(val.encode()).hexdigest()[:8]
                processed_input["code_lines"] = len(val.split('\n'))
            else:
                processed_input[key] = val

        data = {
            "tool": tool,
            "input": processed_input,
            "status": "success" if result and result.get("success") else "error",
            "error_type": error_type
        }

        if result:
            if result.get("success"):
                # Summarize output instead of full dump
                output = result.get("output", {})
                if isinstance(output, dict):
                    data["output_keys"] = list(output.keys())
                    if "results" in output:
                        data["results_summary"] = {k: v for k, v in output["results"].items() if isinstance(v, (int, float))}
            else:
                data["error_msg"] = result.get("error", "Unknown")[:200]  # Truncate long errors

        self.log_event(
            agent="executor",
            event_type="tool_call",
            step_name=step_name,
            data=data,
            duration_ms=duration_ms
        )

    def log_iteration(
        self,
        iteration: int,
        status: str,
        step_name: str = "iteration",
        metadata: Optional[Dict] = None
    ):
        """
        Log an iteration in the multi-turn loop.

        Args:
            iteration: Iteration number
            status: Status (started, completed, failed)
            step_name: Semantic step label
            metadata: Additional iteration context
        """
        data = {
            "iteration": iteration,
            "status": status
        }
        if metadata:
            data.update(metadata)

        self.log_event(
            agent="orchestrator",
            event_type="iteration",
            step_name=step_name,
            data=data
        )

    def log_error(
        self,
        agent: str,
        error_type: str,
        error_msg: str,
        step_name: str = "error",
        stacktrace: Optional[str] = None
    ):
        """
        Log an error event.

        Args:
            agent: Agent where error occurred
            error_type: Error category (timeout, api_error, schema_error, etc.)
            error_msg: Error message
            step_name: Semantic step label
            stacktrace: Optional full stacktrace
        """
        data = {
            "error_type": error_type,
            "error_msg": error_msg[:500],  # Truncate very long messages
        }
        if stacktrace:
            data["stacktrace"] = stacktrace[:1000]

        self.log_event(
            agent=agent,
            event_type="error",
            step_name=step_name,
            data=data
        )

    def log_assumption(
        self,
        parameter: str,
        assumed_value: Any,
        rationale: str,
        fallback_level: int = 1,
        step_name: str = "assumption"
    ):
        """
        Log an assumption made during simulation setup (Phase 3.5).

        Args:
            parameter: Parameter name (e.g., 'location', 'met_source', 'tilt')
            assumed_value: Value that was assumed
            rationale: Explanation for why this default was chosen
            fallback_level: Fallback level at which assumption was made (1=detailed, 2=PVWatts, etc.)
            step_name: Semantic step label
        """
        data = {
            "parameter": parameter,
            "assumed_value": str(assumed_value),
            "rationale": rationale,
            "fallback_level": fallback_level
        }

        self.log_event(
            agent="clarifier",
            event_type="assumption",
            step_name=step_name,
            data=data
        )

    def log_reproducibility_report(
        self,
        report: str,
        assumptions_count: int,
        errors_count: int,
        fallback_level: int,
        step_name: str = "reproducibility"
    ):
        """
        Log reproducibility report summary (Phase 3.5).

        Args:
            report: Full reproducibility report (markdown)
            assumptions_count: Number of assumptions made
            errors_count: Number of errors encountered
            fallback_level: Final fallback level used
            step_name: Semantic step label
        """
        data = {
            "assumptions_count": assumptions_count,
            "errors_count": errors_count,
            "fallback_level": fallback_level,
            "report_length": len(report)
        }

        # Store full report in data for retrieval
        if self.log_file:
            # Write full report as separate entry
            report_entry = {
                "timestamp": datetime.now().isoformat(),
                "elapsed_s": round(time.time() - self.session_start, 3),
                "session_id": self.session_id,
                "agent": "orchestrator",
                "event_type": "reproducibility_full_report",
                "step_name": step_name,
                "report": report
            }
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(report_entry) + "\n")

        self.log_event(
            agent="orchestrator",
            event_type="reproducibility_summary",
            step_name=step_name,
            data=data
        )

    def save_session_summary(self, final_result: Dict):
        """
        Save a session summary at the end (Phase 3.5 enhanced).

        Args:
            final_result: Final result from orchestrator
        """
        data = {
            "success": final_result.get("success"),
            "iterations": final_result.get("iterations", 0),
            "total_duration_s": round(time.time() - self.session_start, 2),
            # Phase 3.5: Include assumption tracking
            "assumptions_made": len(final_result.get("recorded_assumptions", [])),
            "fallback_level": final_result.get("fallback_level", 1),
            "ambiguity_detected": final_result.get("ambiguity_detected", False)
        }

        # Log reproducibility report if available
        if "reproducibility_report" in final_result and final_result["reproducibility_report"]:
            self.log_reproducibility_report(
                report=final_result["reproducibility_report"],
                assumptions_count=len(final_result.get("recorded_assumptions", [])),
                errors_count=len(final_result.get("errors", [])) if "errors" in final_result else 0,
                fallback_level=final_result.get("fallback_level", 1)
            )

        self.log_event(
            agent="orchestrator",
            event_type="session_end",
            step_name="session_summary",
            data=data
        )
