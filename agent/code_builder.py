"""
Code Builder Agent - Generates pvlib simulation code from canonical PV spec.

Responsibilities:
1. Convert CanonicalPVSpec JSON -> executable Python code
2. Apply physics-aware heuristics for mesh, solver config
3. Use domain-specific templates for code generation
4. Ensure code outputs JSON in expected schema format
"""

import json
from typing import Dict, Any, Optional
from agent.schemas.pv_spec_schema import CanonicalPVSpec, TaskType, TrackerMode


class CodeBuilderAgent:
    """Agent that generates pvlib simulation code from PV specifications."""

    CODE_TEMPLATE_ANNUAL_YIELD = """import pvlib
import pandas as pd
import json
from pvlib.pvsystem import pvwatts_dc, pvwatts_losses
from pvlib.temperature import sapm_cell, pvsyst_cell

# Site configuration
lat, lon = {latitude}, {longitude}
tz = '{timezone}'
altitude = {altitude}

# Time range for simulation
times = pd.date_range('{start_date}', '{end_date}', freq='{freq}', tz=tz)
location = pvlib.location.Location(lat, lon, tz=tz, altitude=altitude)

# Solar geometry
solar_pos = location.get_solarposition(times)

# Irradiance data
{irradiance_code}

# POA (Plane of Array) irradiance
from pvlib.irradiance import get_total_irradiance
poa = get_total_irradiance(
    surface_tilt={tilt},
    surface_azimuth={azimuth},
    solar_zenith=solar_pos['zenith'],
    solar_azimuth=solar_pos['azimuth'],
    dni=irrad_data['dni'],
    ghi=irrad_data['ghi'],
    dhi=irrad_data['dhi'],
    albedo=0.2
)

# Temperature model
{temperature_code}

# DC power
pdc0 = {dc_capacity}  # Watts DC
gamma_pdc = -0.004  # Temperature coefficient
dc_power = pvwatts_dc(poa['poa_global'], temp_cell, pdc0=pdc0, gamma_pdc=gamma_pdc)

# Losses and AC power
losses_pct = {losses_percent}
dc_ac_ratio = {dc_ac_ratio}
ac_nominal = pdc0 / dc_ac_ratio
inverter_eff = 0.96

ac_power = dc_power * (1 - losses_pct/100) * inverter_eff
ac_power = ac_power.clip(upper=ac_nominal)  # Inverter clipping

# Results
{results_code}

# Output JSON
result = {result_dict}
print(json.dumps(result))
"""

    # Phase 3.2: Simplified PVWatts template (Fallback Level 2)
    CODE_TEMPLATE_PVWATTS_SIMPLE = """import pvlib
import pandas as pd
import json

# Site configuration
lat, lon = {latitude}, {longitude}
tz = '{timezone}'

# Time range (monthly for speed)
times = pd.date_range('{start_date}', '{end_date}', freq='1h', tz=tz)
location = pvlib.location.Location(lat, lon, tz=tz)

# Clearsky irradiance (simplified)
irrad_data = location.get_clearsky(times, model='ineichen')

# PVWatts simplified model
from pvlib.pvsystem import pvwatts_dc
pdc0 = {dc_capacity}  # Watts DC
dc_power = pvwatts_dc(irrad_data['ghi'], temp_air=25, pdc0=pdc0)

# Simple losses
losses_pct = {losses_percent}
ac_power = dc_power * (1 - losses_pct/100) * 0.96

# Results
annual_kwh = ac_power.sum() / 1000
dc_kw = pdc0 / 1000
hours = len(times)
capacity_factor = annual_kwh / (dc_kw * hours)

result = {{
    "annual_kwh": round(annual_kwh, 2),
    "capacity_factor": round(capacity_factor, 3),
    "location": {{"lat": lat, "lon": lon, "name": "{location_name}"}},
    "system": {{"dc_kw": dc_kw, "tilt": {tilt}, "azimuth": {azimuth}}},
    "note": "Simplified PVWatts model (fallback level 2)"
}}
print(json.dumps(result))
"""

    # Phase 3.2: Constant irradiance approximation (Fallback Level 3)
    CODE_TEMPLATE_CONSTANT_IRRAD = """import json

# Constant irradiance approximation (no pvlib required)
lat, lon = {latitude}, {longitude}
dc_kw = {dc_capacity} / 1000

# Typical solar resource by latitude
if abs(lat) < 23.5:  # Tropics
    peak_sun_hours = 5.5
elif abs(lat) < 45:  # Mid-latitudes
    peak_sun_hours = 4.5
else:  # High latitudes
    peak_sun_hours = 3.5

# Annual energy estimate
annual_kwh = dc_kw * peak_sun_hours * 365 * 0.75  # 75% performance ratio

result = {{
    "annual_kwh": round(annual_kwh, 2),
    "capacity_factor": round(annual_kwh / (dc_kw * 8760), 3),
    "location": {{"lat": lat, "lon": lon, "name": "{location_name}"}},
    "system": {{"dc_kw": dc_kw}},
    "note": "Simplified constant irradiance approximation (fallback level 3)",
    "warning": "This is a rough estimate. Use with caution."
}}
print(json.dumps(result))
"""

    CODE_TEMPLATE_COMPARISON = """import pvlib
import pandas as pd
import json
from pvlib.pvsystem import pvwatts_dc, pvwatts_losses
from pvlib.temperature import sapm_cell, pvsyst_cell

# Site configuration
lat, lon = {latitude}, {longitude}
tz = '{timezone}'
altitude = {altitude}

# Time range for simulation
times = pd.date_range('{start_date}', '{end_date}', freq='{freq}', tz=tz)
location = pvlib.location.Location(lat, lon, tz=tz, altitude=altitude)

# Solar geometry
solar_pos = location.get_solarposition(times)

# Irradiance data
{irradiance_code}

# Simulate multiple configurations
systems = []

{systems_code}

# Output JSON
result = {{"systems": systems}}
print(json.dumps(result))
"""

    def __init__(self, llm_client=None):
        """Initialize Code Builder Agent.

        Args:
            llm_client: Optional LLM client for dynamic code generation.
                       If None, uses template-based generation.
        """
        self.llm_client = llm_client

    def build_code(self, pv_spec: CanonicalPVSpec) -> str:
        """Generate Python code from canonical PV spec.

        Args:
            pv_spec: Validated canonical PV specification

        Returns:
            Executable Python code string
        """
        if pv_spec.output.task_type == TaskType.ANNUAL_YIELD:
            return self._build_annual_yield_code(pv_spec)
        elif pv_spec.output.task_type == TaskType.COMPARISON:
            return self._build_comparison_code(pv_spec)
        else:
            raise NotImplementedError(f"Task type {pv_spec.output.task_type} not yet supported in Phase 2")

    def _build_annual_yield_code(self, spec: CanonicalPVSpec) -> str:
        """Generate code for annual yield calculation."""

        # Determine date range based on task
        start_date = '2024-01-01'
        end_date = '2024-12-31'
        freq = spec.met.resolution

        # Irradiance code
        if spec.met.source == "clearsky":
            irradiance_code = f"irrad_data = location.get_clearsky(times, model='ineichen')"
        else:
            raise NotImplementedError(f"Met source {spec.met.source} not yet supported")

        # Temperature model code
        if spec.system.temp_model == "sapm":
            temp_params = spec.system.temp_params or {'a': -3.47, 'b': -0.0594, 'deltaT': 3}
            temperature_code = f"""# SAPM cell temperature
temp_params = {temp_params}
temp_cell = sapm_cell(
    poa['poa_global'],
    temp_air=25,  # Assume 25°C ambient
    wind_speed=1,  # Light wind
    **temp_params
)"""
        elif spec.system.temp_model == "pvsyst":
            temperature_code = f"""# PVsyst cell temperature
temp_cell = pvsyst_cell(
    poa['poa_global'],
    temp_air=25,
    wind_speed=1
)"""
        else:
            # Default to constant 25°C
            temperature_code = "temp_cell = pd.Series(25, index=times)"

        # Results calculation
        results_code = """annual_kwh = ac_power.sum() / 1000  # Wh to kWh
hours_in_year = len(times)
dc_capacity_kw = pdc0 / 1000
capacity_factor = annual_kwh / (dc_capacity_kw * hours_in_year)"""

        result_dict = """{
    "annual_kwh": round(annual_kwh, 2),
    "capacity_factor": round(capacity_factor, 3),
    "location": {"lat": lat, "lon": lon, "name": "%s"},
    "system": {"dc_kw": dc_capacity_kw, "tilt": %s, "azimuth": %s}
}""" % (spec.site.name or "Unnamed", spec.system.tilt_deg, spec.system.azimuth_deg)

        # Fill template
        code = self.CODE_TEMPLATE_ANNUAL_YIELD.format(
            latitude=spec.site.latitude,
            longitude=spec.site.longitude,
            timezone=spec.site.timezone,
            altitude=spec.site.altitude or 0,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            irradiance_code=irradiance_code,
            tilt=spec.system.tilt_deg,
            azimuth=spec.system.azimuth_deg,
            temperature_code=temperature_code,
            dc_capacity=spec.system.dc_capacity_w,
            losses_percent=spec.system.losses_percent or 14.0,
            dc_ac_ratio=spec.system.dc_ac_ratio or 1.2,
            results_code=results_code,
            result_dict=result_dict
        )

        return code

    def _build_comparison_code(self, spec: CanonicalPVSpec) -> str:
        """Generate code for system comparison."""

        start_date = '2024-01-01'
        end_date = '2024-12-31'
        freq = spec.met.resolution

        # Irradiance code
        if spec.met.source == "clearsky":
            irradiance_code = "irrad_data = location.get_clearsky(times, model='ineichen')"
        else:
            raise NotImplementedError(f"Met source {spec.met.source} not supported")

        # Generate code for each system configuration
        # For comparison, typically fixed vs tracking
        systems_code_parts = []

        # Fixed tilt system
        systems_code_parts.append(f"""
# System 1: Fixed tilt
poa_fixed = get_total_irradiance(
    surface_tilt={spec.system.tilt_deg},
    surface_azimuth={spec.system.azimuth_deg},
    solar_zenith=solar_pos['zenith'],
    solar_azimuth=solar_pos['azimuth'],
    dni=irrad_data['dni'],
    ghi=irrad_data['ghi'],
    dhi=irrad_data['dhi'],
    albedo=0.2
)
temp_cell_fixed = pvsyst_cell(poa_fixed['poa_global'], temp_air=25, wind_speed=1)
dc_fixed = pvwatts_dc(poa_fixed['poa_global'], temp_cell_fixed, pdc0={spec.system.dc_capacity_w}, gamma_pdc=-0.004)
ac_fixed = dc_fixed * (1 - {spec.system.losses_percent or 14.0}/100) * 0.96
annual_kwh_fixed = ac_fixed.sum() / 1000
cf_fixed = annual_kwh_fixed / ({spec.system.dc_capacity_w}/1000 * len(times))

systems.append({{
    "name": "Fixed Tilt",
    "tracker_mode": "fixed",
    "annual_kwh": round(annual_kwh_fixed, 2),
    "capacity_factor": round(cf_fixed, 3)
}})
""")

        # Single-axis tracking system
        systems_code_parts.append(f"""
# System 2: Single-axis tracker
from pvlib.tracking import singleaxis
tracker_data = singleaxis(
    solar_pos['apparent_zenith'],
    solar_pos['azimuth'],
    axis_tilt=0,
    axis_azimuth=180,  # N-S aligned
    max_angle=90,
    backtrack=True,
    gcr=0.35
)
poa_tracker = get_total_irradiance(
    surface_tilt=tracker_data['surface_tilt'],
    surface_azimuth=tracker_data['surface_azimuth'],
    solar_zenith=solar_pos['zenith'],
    solar_azimuth=solar_pos['azimuth'],
    dni=irrad_data['dni'],
    ghi=irrad_data['ghi'],
    dhi=irrad_data['dhi'],
    albedo=0.2
)
temp_cell_tracker = pvsyst_cell(poa_tracker['poa_global'], temp_air=25, wind_speed=1)
dc_tracker = pvwatts_dc(poa_tracker['poa_global'], temp_cell_tracker, pdc0={spec.system.dc_capacity_w}, gamma_pdc=-0.004)
ac_tracker = dc_tracker * (1 - {spec.system.losses_percent or 14.0}/100) * 0.96
annual_kwh_tracker = ac_tracker.sum() / 1000
cf_tracker = annual_kwh_tracker / ({spec.system.dc_capacity_w}/1000 * len(times))

systems.append({{
    "name": "Single-Axis Tracker",
    "tracker_mode": "single_axis",
    "annual_kwh": round(annual_kwh_tracker, 2),
    "capacity_factor": round(cf_tracker, 3)
}})
""")

        systems_code = "\n".join(systems_code_parts)

        code = self.CODE_TEMPLATE_COMPARISON.format(
            latitude=spec.site.latitude,
            longitude=spec.site.longitude,
            timezone=spec.site.timezone,
            altitude=spec.site.altitude or 0,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            irradiance_code=irradiance_code,
            systems_code=systems_code
        )

        return code

    def build_pvwatts_simple(self, pv_spec: CanonicalPVSpec) -> str:
        """Generate simplified PVWatts code (Fallback Level 2).

        Args:
            pv_spec: PV specification

        Returns:
            Simplified PVWatts Python code
        """
        code = self.CODE_TEMPLATE_PVWATTS_SIMPLE.format(
            latitude=pv_spec.site.latitude,
            longitude=pv_spec.site.longitude,
            timezone=pv_spec.site.timezone,
            start_date='2024-01-01',
            end_date='2024-12-31',
            dc_capacity=pv_spec.system.dc_capacity_w,
            losses_percent=pv_spec.system.losses_percent or 14.0,
            tilt=pv_spec.system.tilt_deg,
            azimuth=pv_spec.system.azimuth_deg,
            location_name=pv_spec.site.name or "Unnamed"
        )
        return code

    def build_constant_irrad(self, pv_spec: CanonicalPVSpec) -> str:
        """Generate constant irradiance approximation (Fallback Level 3).

        Args:
            pv_spec: PV specification

        Returns:
            Constant irradiance approximation Python code
        """
        code = self.CODE_TEMPLATE_CONSTANT_IRRAD.format(
            latitude=pv_spec.site.latitude,
            longitude=pv_spec.site.longitude,
            dc_capacity=pv_spec.system.dc_capacity_w,
            location_name=pv_spec.site.name or "Unnamed"
        )
        return code

    def validate_code_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Validate Python syntax without executing.

        Args:
            code: Python code string

        Returns:
            (is_valid, error_message)
        """
        try:
            compile(code, '<string>', 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.msg}"
