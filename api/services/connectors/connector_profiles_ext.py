"""Extended connector tool profiles assembled from section modules."""
from __future__ import annotations

from api.services.connectors.connector_profiles_ext_sections.foundation_business import PROFILES_EXT_FOUNDATION_BUSINESS
from api.services.connectors.connector_profiles_ext_sections.foundation_core import PROFILES_EXT_FOUNDATION_CORE
from api.services.connectors.connector_profiles_ext_sections.tier1 import PROFILES_EXT_TIER1
from api.services.connectors.connector_profiles_ext_sections.tier2 import PROFILES_EXT_TIER2
from api.services.connectors.connector_profiles_ext_sections.tier3 import PROFILES_EXT_TIER3

PROFILES_EXT: dict[str, dict] = {
    **PROFILES_EXT_FOUNDATION_CORE,
    **PROFILES_EXT_FOUNDATION_BUSINESS,
    **PROFILES_EXT_TIER1,
    **PROFILES_EXT_TIER2,
    **PROFILES_EXT_TIER3,
}
