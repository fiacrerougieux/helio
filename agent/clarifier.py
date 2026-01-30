"""
Input Clarifier Agent - Converts natural language to canonical PV spec.

Responsibilities:
1. Extract location, system params, task type from user prompt
2. Fill in missing assumptions with sensible defaults
3. Generate canonical PV spec JSON
4. Validate spec completeness
"""

import json
from typing import Tuple, Optional, List
from agent.schemas.pv_spec_schema import (
    CanonicalPVSpec, SiteSpec, MetSpec, SystemSpec, OutputSpec,
    TaskType, MetSource, TrackerMode, TempModel
)


class ClarifierAgent:
    """Agent that converts user prompts into canonical PV specifications."""

    CLARIFIER_PROMPT = """You are a PV simulation specification clarifier.

Your job: Convert the user's natural language request into a complete, unambiguous PV simulation specification.

INPUT: User prompt (may be underspecified)
OUTPUT: Canonical PV spec JSON + list of assumptions

Rules:
1. Extract explicit parameters from user prompt
2. For missing parameters, choose sensible defaults based on:
   - Location (e.g., Sydney -> tilt~=latitude, azimuth=0 for N hemisphere tilt north)
   - Task type (comparison needs matching schemas, sensitivity needs range)
   - Industry standards (14% system losses, 1.2 DC/AC ratio)
3. Document ALL assumptions in the "assumptions" field
4. If task type is COMPARISON, ensure output schema supports comparison structure
5. Temperature model defaults:
   - Use SAPM if location has NSRDB data available (US locations)
   - Use PVSYST otherwise (simpler, fewer params)
   - Document temp model choice in assumptions

Location Guidelines:
- If city name given, infer lat/lon (e.g., "Sydney" -> -33.86, 151.21)
- Infer timezone from location (e.g., Sydney -> "Australia/Sydney")
- Default altitude to 0 if not specified

Orientation Guidelines:
- Fixed tilt systems:
  * Tilt = latitude (optimal for year-round in most climates)
  * Azimuth = 180° (south) in Northern Hemisphere
  * Azimuth = 0° (north) in Southern Hemisphere
- Tracker systems:
  * Single-axis: N-S aligned (most common)
  * Dual-axis: No tilt/azimuth needed (tracks sun)

Task Type Detection:
- "annual energy", "yearly output" -> ANNUAL_YIELD
- "compare", "vs", "versus" -> COMPARISON
- "sensitivity", "impact of", "effect of" -> SENSITIVITY
- "capacity factor", "CF" -> CAPACITY_FACTOR
- "monthly", "seasonal" -> MONTHLY_PROFILE

Output Schema Guidelines:
- ANNUAL_YIELD: {{"annual_kwh": float, "capacity_factor": float}}
- COMPARISON: {{"systems": [{{"name": str, "annual_kwh": float, "capacity_factor": float}}]}}
- SENSITIVITY: {{"sensitivity": [{{"variable": str, "value": float, "annual_kwh": float}}]}}
- CAPACITY_FACTOR: {{"capacity_factor": float, "annual_kwh": float}}
- MONTHLY_PROFILE: {{"monthly_kwh": [float], "months": [str]}}

Examples:

Example 1:
User: "10 kW system in Sydney, annual energy"
Output:
{{
  "site": {{
    "latitude": -33.86,
    "longitude": 151.21,
    "timezone": "Australia/Sydney",
    "altitude": 0,
    "name": "Sydney"
  }},
  "met": {{
    "source": "clearsky",
    "resolution": "1h"
  }},
  "system": {{
    "dc_capacity_w": 10000,
    "tilt_deg": 33.86,
    "azimuth_deg": 0,
    "tracker_mode": "fixed",
    "dc_ac_ratio": 1.2,
    "losses_percent": 14.0,
    "temp_model": "pvsyst"
  }},
  "output": {{
    "task_type": "annual_yield",
    "schema": {{
      "annual_kwh": "float",
      "capacity_factor": "float"
    }},
    "units": {{
      "annual_kwh": "kWh",
      "capacity_factor": "dimensionless"
    }}
  }},
  "assumptions": [
    "Tilt set to latitude (33.86°) for optimal year-round performance",
    "Azimuth=0° (north-facing in Southern Hemisphere)",
    "Clearsky weather data used",
    "PVsyst temperature model (simpler than SAPM)",
    "14% system losses (industry standard)",
    "1.2 DC/AC ratio (common for residential)"
  ]
}}

Example 2:
User: "Compare 10kW fixed vs tracking in Denver"
Output:
{{
  "site": {{
    "latitude": 39.74,
    "longitude": -104.99,
    "timezone": "America/Denver",
    "altitude": 1609,
    "name": "Denver"
  }},
  "met": {{
    "source": "clearsky",
    "resolution": "1h"
  }},
  "system": {{
    "dc_capacity_w": 10000,
    "tilt_deg": 39.74,
    "azimuth_deg": 180,
    "tracker_mode": "fixed",
    "dc_ac_ratio": 1.2,
    "losses_percent": 14.0,
    "temp_model": "sapm"
  }},
  "output": {{
    "task_type": "comparison",
    "schema": {{
      "systems": [
        {{
          "name": "str",
          "tracker_mode": "str",
          "annual_kwh": "float",
          "capacity_factor": "float"
        }}
      ]
    }},
    "units": {{
      "annual_kwh": "kWh",
      "capacity_factor": "dimensionless"
    }}
  }},
  "assumptions": [
    "Compare fixed-tilt (latitude tilt, south-facing) vs single-axis N-S tracker",
    "Same DC capacity (10 kW) and losses (14%) for both systems",
    "SAPM temperature model (Denver is in US, NSRDB data available)",
    "Clearsky weather data for fair comparison"
  ],
  "constraints": [
    "Same weather data for both systems",
    "Output must include tracker_mode for identification"
  ]
}}

Example 3:
User: "Temperature sensitivity for Phoenix rooftop"
Output:
{{
  "site": {{
    "latitude": 33.45,
    "longitude": -112.07,
    "timezone": "America/Phoenix",
    "altitude": 331,
    "name": "Phoenix"
  }},
  "met": {{
    "source": "clearsky",
    "resolution": "1h"
  }},
  "system": {{
    "dc_capacity_w": 5000,
    "tilt_deg": 33.45,
    "azimuth_deg": 180,
    "tracker_mode": "fixed",
    "dc_ac_ratio": 1.2,
    "losses_percent": 14.0,
    "temp_model": "noct"
  }},
  "output": {{
    "task_type": "sensitivity",
    "schema": {{
      "sensitivity": [
        {{
          "temp_model": "str",
          "annual_kwh": "float",
          "avg_cell_temp_c": "float"
        }}
      ]
    }},
    "units": {{
      "annual_kwh": "kWh",
      "avg_cell_temp_c": "°C"
    }}
  }},
  "assumptions": [
    "Rooftop installation -> use NOCT as baseline temp model",
    "Test sensitivity across temp models: SAPM, PVsyst, Faiman, NOCT",
    "Default 5 kW system (typical residential rooftop)",
    "Phoenix climate (hot, high temp impact)"
  ]
}}

Now process this user request:
{user_prompt}

Return JSON in this exact format:
{{
  "pv_spec": <CanonicalPVSpec JSON>,
  "clarification_summary": "<1-2 sentence natural language summary of what will be simulated>"
}}

IMPORTANT: Return ONLY valid JSON. Do not include markdown code blocks or explanations.
"""

    def __init__(self, llm_client, logger=None):
        """
        Initialize Clarifier agent.

        Args:
            llm_client: LLM client (must support structured output via response_schema)
            logger: Optional StructuredLogger for observability
        """
        self.llm = llm_client
        self.logger = logger

    def clarify(self, user_prompt: str) -> Tuple[CanonicalPVSpec, str]:
        """
        Convert user prompt to canonical PV spec.

        Args:
            user_prompt: Natural language request from user

        Returns:
            (pv_spec, clarification_summary)

        Raises:
            ValueError: If LLM returns invalid spec or fails validation
        """
        # Format prompt
        prompt = self.CLARIFIER_PROMPT.format(user_prompt=user_prompt)

        # Log start
        if self.logger:
            self.logger.log_event("clarifier", "start", {"prompt_length": len(user_prompt)})

        # Call LLM (without response_schema for now - varies by provider)
        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2  # Low temp for consistency
            )

            # Debug: log response type and content
            if self.logger:
                self.logger.log_event("clarifier", "llm_response", {
                    "response_type": type(response).__name__,
                    "response_preview": str(response)[:200] if response else "None"
                })

            # Parse response (handle both string and dict responses)
            if isinstance(response, dict):
                # Ollama-compatible dict format
                if "message" in response:
                    response = response["message"]["content"]
                else:
                    # Already parsed dict
                    result = response

            if isinstance(response, str):
                if not response or response.isspace():
                    raise ValueError("LLM returned empty response")
                result = json.loads(response)
            else:
                result = response

            pv_spec_dict = result["pv_spec"]
            summary = result["clarification_summary"]

            # Validate with Pydantic
            pv_spec = CanonicalPVSpec(**pv_spec_dict)

            # Additional validation
            validation_error = self.validate_spec(pv_spec)
            if validation_error:
                raise ValueError(f"Spec validation failed: {validation_error}")

            # Log success
            if self.logger:
                self.logger.log_event("clarifier", "complete", {
                    "task_type": pv_spec.output.task_type.value,
                    "assumptions_count": len(pv_spec.assumptions),
                    "tracker_mode": pv_spec.system.tracker_mode.value
                })

            return pv_spec, summary

        except json.JSONDecodeError as e:
            error_msg = f"LLM returned invalid JSON: {e}"
            if self.logger:
                self.logger.log_event("clarifier", "error", {"error": error_msg})
            raise ValueError(error_msg)

        except Exception as e:
            error_msg = f"Clarification failed: {str(e)}"
            if self.logger:
                self.logger.log_event("clarifier", "error", {"error": error_msg})
            raise ValueError(error_msg)

    def validate_spec(self, spec: CanonicalPVSpec) -> Optional[str]:
        """
        Validate PV spec for completeness and consistency.

        Returns:
            None if valid, error message if invalid
        """
        # Note: Most validation is done by Pydantic validators in the schema
        # This is for additional cross-field validation

        # Check met source requirements
        if spec.met.source in [MetSource.TMY, MetSource.ERA5]:
            if spec.met.year is None:
                return f"{spec.met.source.value} requires year to be specified"

        # Check comparison task has enough info
        if spec.output.task_type == TaskType.COMPARISON:
            if 'systems' not in spec.output.schema:
                return "Comparison task requires 'systems' in output schema"

        # Check sensitivity task
        if spec.output.task_type == TaskType.SENSITIVITY:
            if 'sensitivity' not in spec.output.schema:
                return "Sensitivity task requires 'sensitivity' in output schema"

        return None

    def validate_location(self, latitude: float, longitude: float) -> bool:
        """
        Validate that location coordinates are reasonable.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            True if valid, False otherwise
        """
        # Basic bounds check (already done by Pydantic, but extra safety)
        if not (-90 <= latitude <= 90):
            return False
        if not (-180 <= longitude <= 180):
            return False

        # Check not in ocean (very rough heuristic - just check not in middle of Pacific)
        # This is a simple check - real geocoding would be better
        if -180 <= longitude <= -140 and -40 <= latitude <= 40:
            # Likely middle of Pacific Ocean
            return False

        return True

    def infer_climate_zone(self, latitude: float) -> str:
        """
        Infer climate zone from latitude (rough heuristic).

        Args:
            latitude: Latitude in decimal degrees

        Returns:
            Climate zone: tropical, arid, temperate, continental, polar
        """
        abs_lat = abs(latitude)

        if abs_lat < 23.5:
            return "tropical"
        elif abs_lat < 35:
            return "arid"  # Subtropical, often arid
        elif abs_lat < 50:
            return "temperate"
        elif abs_lat < 66.5:
            return "continental"
        else:
            return "polar"

    # Phase 3.3: Human-in-Loop Only for Ambiguity
    def detect_ambiguity(self, user_query: str, pv_spec: Optional[CanonicalPVSpec] = None) -> Optional[str]:
        """
        Detect if user query is underspecified and requires clarification.

        Phase 3.3 Pattern: Only prompt user when PVSpec cannot be completed safely.
        Otherwise, pick documented defaults and record them.

        Args:
            user_query: Original user prompt
            pv_spec: PV spec (if already generated, otherwise will check query)

        Returns:
            Clarifying question for user, or None if spec is complete
        """
        ambiguities = []

        # Check location
        if pv_spec is None or not self._has_valid_location(pv_spec):
            if not self._can_infer_location(user_query):
                ambiguities.append("location")

        # Check timeframe for annual/monthly tasks
        if pv_spec and pv_spec.output.task_type in [TaskType.ANNUAL_YIELD, TaskType.MONTHLY_PROFILE]:
            if not self._has_explicit_timeframe(user_query):
                # We can assume a full year, but check if query suggests specific year
                if any(keyword in user_query.lower() for keyword in ['2023', '2024', '2025', 'last year', 'this year']):
                    ambiguities.append("timeframe")

        if ambiguities:
            return self._generate_clarifying_question(ambiguities, user_query)

        return None

    def _has_valid_location(self, pv_spec: CanonicalPVSpec) -> bool:
        """Check if PV spec has valid location data."""
        return (
            pv_spec.site is not None and
            pv_spec.site.latitude is not None and
            pv_spec.site.longitude is not None and
            self.validate_location(pv_spec.site.latitude, pv_spec.site.longitude)
        )

    def _can_infer_location(self, user_query: str) -> bool:
        """
        Check if location can be inferred from user query.

        Returns True if query contains recognizable location keywords.
        """
        query_lower = user_query.lower()

        # Common city names and location indicators
        location_keywords = [
            'sydney', 'melbourne', 'brisbane', 'perth', 'adelaide',  # Australia
            'new york', 'los angeles', 'chicago', 'houston', 'phoenix', 'denver', 'boston', 'seattle',  # US
            'london', 'paris', 'berlin', 'madrid', 'rome',  # Europe
            'tokyo', 'beijing', 'singapore', 'mumbai', 'delhi',  # Asia
            'latitude', 'longitude', 'lat', 'lon', '°n', '°s', '°e', '°w'  # Explicit coords
        ]

        return any(keyword in query_lower for keyword in location_keywords)

    def _has_explicit_timeframe(self, user_query: str) -> bool:
        """
        Check if query has explicit timeframe.

        Returns True if query specifies time period.
        """
        query_lower = user_query.lower()

        timeframe_keywords = [
            '2020', '2021', '2022', '2023', '2024', '2025',  # Specific years
            'january', 'february', 'march', 'april', 'may', 'june',  # Months
            'july', 'august', 'september', 'october', 'november', 'december',
            'q1', 'q2', 'q3', 'q4',  # Quarters
            'summer', 'winter', 'spring', 'fall', 'autumn'  # Seasons
        ]

        # "annual" without year is NOT explicit
        return any(keyword in query_lower for keyword in timeframe_keywords)

    def _generate_clarifying_question(self, ambiguities: List[str], user_query: str) -> str:
        """
        Generate user-facing clarifying question for ambiguous queries.

        Args:
            ambiguities: List of ambiguous parameters (e.g., ['location'])
            user_query: Original user query for context

        Returns:
            Clarifying question string
        """
        if len(ambiguities) == 1:
            if ambiguities[0] == "location":
                return (
                    "I need to know the system location to provide accurate results. "
                    "Where is the PV system located? (city name or latitude/longitude)"
                )
            elif ambiguities[0] == "timeframe":
                return (
                    "Which year should I use for the simulation? "
                    "(e.g., 2024, or I can use a typical year)"
                )
        else:
            # Multiple ambiguities
            questions = []
            if "location" in ambiguities:
                questions.append("- System location (city or coordinates)")
            if "timeframe" in ambiguities:
                questions.append("- Time period (year or season)")

            return (
                "I need some additional information:\n" +
                "\n".join(questions)
            )
