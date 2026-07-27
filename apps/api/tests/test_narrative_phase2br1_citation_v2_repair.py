"""CHG-058 — named Citation Repair product scenarios (HTTP Replay B/C)."""

from __future__ import annotations

import pytest

# Pull product_env fixture from the CHG-057 harness module.
pytest_plugins = ["tests.test_narrative_phase2br1_chg057_acceptance_closure"]

from tests.test_narrative_phase2br1_citation_v2_http_replay import (  # noqa: E402
    test_citation_v2_scenario_b_unknown_then_repair,
    test_citation_v2_scenario_c_repair_still_invalid,
)

__all__ = [
    "test_citation_v2_scenario_b_unknown_then_repair",
    "test_citation_v2_scenario_c_repair_still_invalid",
]
