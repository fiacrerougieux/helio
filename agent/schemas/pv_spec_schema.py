"""
Canonical PV Specification Schema.

Defines the complete, unambiguous specification for a PV simulation task.
This schema serves as the contract between the Clarifier and downstream agents.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List, Dict, Any
from enum import Enum


class MetSource(str, Enum):
    """Weather data source."""
    CLEARSKY = "clearsky"
    TMY = "tmy"
    ERA5 = "era5"
    NSRDB = "nsrdb"


class TaskType(str, Enum):
    """Type of simulation task."""
    ANNUAL_YIELD = "annual_yield"
    COMPARISON = "comparison"
    SENSITIVITY = "sensitivity"
    CAPACITY_FACTOR = "capacity_factor"
    FAULT_CHECK = "fault_check"
    MONTHLY_PROFILE = "monthly_profile"


class TrackerMode(str, Enum):
    """Solar tracker configuration."""
    FIXED = "fixed"
    SINGLE_AXIS = "single_axis"
    DUAL_AXIS = "dual_axis"


class TempModel(str, Enum):
    """Temperature model for cell temperature calculation."""
    SAPM = "sapm"  # Sandia Array Performance Model
    PVSYST = "pvsyst"  # PVsyst model
    FAIMAN = "faiman"  # Faiman model
    NOCT = "noct"  # Nominal Operating Cell Temperature
    NONE = "none"  # No temperature modeling


class SiteSpec(BaseModel):
    """Location and timezone specification."""
    latitude: float = Field(..., ge=-90, le=90, description="Site latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Site longitude in decimal degrees")
    timezone: str = Field(..., description="IANA timezone (e.g., 'America/New_York', 'Australia/Sydney')")
    altitude: Optional[float] = Field(None, ge=0, description="Elevation in meters above sea level")
    name: Optional[str] = Field(None, description="Human-readable site name (e.g., 'Denver Office Rooftop')")

    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate IANA timezone format."""
        import pytz
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {v}. Must be IANA timezone (e.g., 'America/New_York')")
        return v


class MetSpec(BaseModel):
    """Weather data specification."""
    source: MetSource = Field(..., description="Weather data source")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="Year for TMY/historical data (required for TMY/ERA5)")
    resolution: str = Field("1h", description="Time resolution (e.g., '1h', '15min', '5min')")

    @field_validator('resolution')
    @classmethod
    def validate_resolution(cls, v: str) -> str:
        """Validate pandas-compatible frequency string."""
        import pandas as pd
        try:
            # Test if valid pandas frequency
            pd.Timedelta(v)
        except ValueError:
            raise ValueError(f"Invalid resolution: {v}. Must be pandas-compatible (e.g., '1h', '15min')")
        return v


class SystemSpec(BaseModel):
    """PV system specification."""
    dc_capacity_w: float = Field(..., gt=0, description="DC nameplate capacity in watts")

    # Orientation (fixed tilt or tracker)
    tilt_deg: Optional[float] = Field(None, ge=0, le=90, description="Surface tilt (0=horizontal, 90=vertical). Required for FIXED mode.")
    azimuth_deg: Optional[float] = Field(None, ge=0, lt=360, description="Surface azimuth (180=south in N hemisphere). Required for FIXED mode.")
    tracker_mode: TrackerMode = Field(TrackerMode.FIXED, description="Tracker configuration")

    # Inverter and losses
    dc_ac_ratio: float = Field(1.2, gt=0, le=5.0, description="DC/AC ratio for inverter sizing")
    losses_percent: float = Field(14.0, ge=0, le=100, description="Total system losses percentage")

    # Temperature modeling
    temp_model: TempModel = Field(TempModel.SAPM, description="Temperature model choice")
    temp_params: Optional[Dict[str, float]] = Field(
        None,
        description="Temperature model parameters (e.g., {'a': -3.47, 'b': -0.0594, 'deltaT': 3} for SAPM)"
    )

    # Module parameters (optional, for detailed modeling)
    module_name: Optional[str] = Field(None, description="Module name from pvlib CEC database")
    inverter_name: Optional[str] = Field(None, description="Inverter name from pvlib CEC database")

    @field_validator('tilt_deg', 'azimuth_deg')
    @classmethod
    def validate_orientation(cls, v: Optional[float], info) -> Optional[float]:
        """Validate orientation is provided for fixed systems."""
        # Note: This validator can't check tracker_mode since it's not available in context
        # We'll do cross-field validation in CanonicalPVSpec
        return v


class OutputSpec(BaseModel):
    """Expected output format specification."""
    task_type: TaskType = Field(..., description="Type of simulation task")
    schema: Dict[str, Any] = Field(..., description="JSON schema for required output fields")
    units: Dict[str, str] = Field(
        default_factory=dict,
        description="Unit specifications for output fields (e.g., {'annual_kwh': 'kWh', 'capacity_factor': 'dimensionless'})"
    )


class CanonicalPVSpec(BaseModel):
    """
    Complete canonical specification for PV simulation task.

    This is the contract between the Clarifier agent and downstream agents.
    All ambiguity should be resolved and all assumptions documented.
    """
    site: SiteSpec
    met: MetSpec
    system: SystemSpec
    output: OutputSpec

    # Metadata
    assumptions: List[str] = Field(
        default_factory=list,
        description="Explicit assumptions made during clarification (e.g., 'Tilt set to latitude', 'SAPM temp model used')"
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="Constraints or requirements from user (e.g., 'Must use TMY data', 'No clipping allowed')"
    )

    @field_validator('system')
    @classmethod
    def validate_system_orientation(cls, v: SystemSpec) -> SystemSpec:
        """Validate that fixed systems have tilt and azimuth."""
        if v.tracker_mode == TrackerMode.FIXED:
            if v.tilt_deg is None or v.azimuth_deg is None:
                raise ValueError("Fixed tilt system requires both tilt_deg and azimuth_deg")
        return v

    @field_validator('system')
    @classmethod
    def validate_temp_params(cls, v: SystemSpec) -> SystemSpec:
        """Validate temperature model parameters if needed."""
        if v.temp_model == TempModel.SAPM and v.temp_params is None:
            # Auto-populate default SAPM params (open-rack glass/cell/glass)
            v.temp_params = {'a': -3.47, 'b': -0.0594, 'deltaT': 3}
        return v

    @field_validator('output')
    @classmethod
    def validate_output_schema(cls, v: OutputSpec, info) -> OutputSpec:
        """Validate output schema matches task type."""
        task_type = v.task_type
        schema = v.schema

        # Check required fields for each task type
        if task_type == TaskType.ANNUAL_YIELD:
            if 'annual_kwh' not in schema:
                raise ValueError("ANNUAL_YIELD task requires 'annual_kwh' in output schema")

        elif task_type == TaskType.COMPARISON:
            if 'systems' not in schema:
                raise ValueError("COMPARISON task requires 'systems' array in output schema")

        elif task_type == TaskType.SENSITIVITY:
            if 'sensitivity' not in schema:
                raise ValueError("SENSITIVITY task requires 'sensitivity' array in output schema")

        elif task_type == TaskType.CAPACITY_FACTOR:
            if 'capacity_factor' not in schema:
                raise ValueError("CAPACITY_FACTOR task requires 'capacity_factor' in output schema")

        elif task_type == TaskType.MONTHLY_PROFILE:
            if 'monthly_kwh' not in schema:
                raise ValueError("MONTHLY_PROFILE task requires 'monthly_kwh' in output schema")

        return v


# Example specs for testing
EXAMPLE_ANNUAL_YIELD_SPEC = CanonicalPVSpec(
    site=SiteSpec(
        latitude=39.74,
        longitude=-104.99,
        timezone="America/Denver",
        altitude=1609,
        name="Denver"
    ),
    met=MetSpec(
        source=MetSource.CLEARSKY,
        resolution="1h"
    ),
    system=SystemSpec(
        dc_capacity_w=10000,
        tilt_deg=39.74,  # Latitude tilt
        azimuth_deg=180,  # South-facing
        tracker_mode=TrackerMode.FIXED,
        dc_ac_ratio=1.2,
        losses_percent=14.0,
        temp_model=TempModel.SAPM
    ),
    output=OutputSpec(
        task_type=TaskType.ANNUAL_YIELD,
        schema={
            "annual_kwh": "float",
            "capacity_factor": "float",
            "peak_power_w": "float"
        },
        units={
            "annual_kwh": "kWh",
            "capacity_factor": "dimensionless",
            "peak_power_w": "W"
        }
    ),
    assumptions=[
        "Tilt set to latitude (39.74°) for optimal year-round performance",
        "Azimuth=180° (south-facing in Northern Hemisphere)",
        "SAPM temperature model with default open-rack parameters",
        "14% system losses (soiling, wiring, connections, etc.)"
    ]
)

EXAMPLE_COMPARISON_SPEC = CanonicalPVSpec(
    site=SiteSpec(
        latitude=39.74,
        longitude=-104.99,
        timezone="America/Denver",
        name="Denver"
    ),
    met=MetSpec(
        source=MetSource.CLEARSKY,
        resolution="1h"
    ),
    system=SystemSpec(
        dc_capacity_w=10000,
        tilt_deg=39.74,  # This will be overridden per system in comparison
        azimuth_deg=180,
        tracker_mode=TrackerMode.FIXED,  # This will vary
        dc_ac_ratio=1.2,
        losses_percent=14.0,
        temp_model=TempModel.SAPM
    ),
    output=OutputSpec(
        task_type=TaskType.COMPARISON,
        schema={
            "systems": [
                {
                    "name": "str",
                    "tracker_mode": "str",
                    "annual_kwh": "float",
                    "capacity_factor": "float"
                }
            ]
        },
        units={
            "annual_kwh": "kWh",
            "capacity_factor": "dimensionless"
        }
    ),
    assumptions=[
        "Compare fixed-tilt vs single-axis tracker",
        "Same DC capacity and losses for both systems",
        "Single-axis tracker aligned N-S"
    ],
    constraints=[
        "Must use same weather data for fair comparison",
        "Output must include tracker_mode for each system"
    ]
)
