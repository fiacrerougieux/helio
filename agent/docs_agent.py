from typing import List, Dict, Any
from agent.tools.introspection import IntrospectionTool
from agent.schemas.api_cards import APICard

# Core pvlib symbols that SimAgent commonly needs.
# Pre-introspecting these at session start prevents API mismatch drift
# (e.g., guessing 'poa' instead of 'poa_irradiance').
CORE_PVLIB_SYMBOLS = [
    # --- PVWatts pipeline (basic) ---
    "pvlib.pvsystem.pvwatts_dc",
    "pvlib.pvsystem.pvwatts_losses",
    "pvlib.irradiance.get_total_irradiance",
    "pvlib.location.Location",
    "pvlib.location.Location.get_solarposition",
    "pvlib.location.Location.get_clearsky",
    "pvlib.solarposition.get_solarposition",
    "pvlib.tracking.singleaxis",
    # --- Temperature models ---
    "pvlib.temperature.sapm_cell",
    "pvlib.temperature.pvsyst_cell",
    "pvlib.temperature.faiman",
    # --- Clearsky models ---
    "pvlib.clearsky.ineichen",
    "pvlib.clearsky.haurwitz",
    # --- IAM (incidence angle modifier) ---
    "pvlib.iam.ashrae",
    "pvlib.iam.physical",
    # --- Single-diode / CEC / SAPM electrical ---
    "pvlib.pvsystem.calcparams_cec",
    "pvlib.pvsystem.calcparams_desoto",
    "pvlib.pvsystem.singlediode",
    "pvlib.pvsystem.i_from_v",
    "pvlib.pvsystem.sapm",
    "pvlib.pvsystem.sapm_effective_irradiance",
    "pvlib.pvsystem.retrieve_sam",
    # --- Inverter models ---
    "pvlib.inverter.sandia",
    "pvlib.inverter.pvwatts",
    # --- Irradiance decomposition & AOI ---
    "pvlib.irradiance.erbs",
    "pvlib.irradiance.disc",
    "pvlib.irradiance.aoi",
    # --- Shading ---
    "pvlib.shading.masking_angle_passias",
    # --- Atmosphere ---
    "pvlib.atmosphere.get_relative_airmass",
    "pvlib.atmosphere.get_absolute_airmass",
]


class DocsAgent:
    """
    The Librarian.
    Responsibilities:
    1. Receive a list of needed API symbols.
    2. Retrieve APICards via introspection (runtime verification).
    3. Pre-seed core pvlib APICards so SimAgent always has correct signatures.
    4. (Future) Supplement with local documentation RAG.
    """

    def __init__(self):
        self.introspection_tool = IntrospectionTool()
        self._core_cards_cache: List[Dict[str, Any]] = []

    def retrieve_cards(self, symbols: List[str]) -> List[APICard]:
        """
        Retrieve API cards for the requested symbols.
        """
        if not symbols:
            return []

        return self.introspection_tool.introspect_many(symbols)

    def retrieve_cards_as_json(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Returns serialized APICards for the SimAgent.
        """
        cards = self.retrieve_cards(symbols)
        return [card.model_dump() for card in cards]

    def get_core_cards(self) -> List[Dict[str, Any]]:
        """
        Pre-introspect core pvlib symbols and return their APICards.

        This prevents API mismatch drift by giving SimAgent the real
        function signatures (e.g., pvwatts_dc expects 'poa_global' not 'poa').
        Results are cached after the first call.
        """
        if self._core_cards_cache:
            return self._core_cards_cache

        cards = self.introspection_tool.introspect_many(CORE_PVLIB_SYMBOLS)
        self._core_cards_cache = [card.model_dump() for card in cards]
        return self._core_cards_cache
