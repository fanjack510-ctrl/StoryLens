"""CHG-058 — named Citation Persistence product scenario (HTTP Replay A)."""

from __future__ import annotations

import pytest

pytest_plugins = ["tests.test_narrative_phase2br1_chg057_acceptance_closure"]

from tests.test_narrative_phase2br1_citation_v2_http_replay import (  # noqa: E402
    test_citation_v2_scenario_a_valid_no_repair,
)

__all__ = ["test_citation_v2_scenario_a_valid_no_repair"]
