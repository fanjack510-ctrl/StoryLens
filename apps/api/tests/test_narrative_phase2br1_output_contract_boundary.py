"""NOT COUNTED FOR CHG-057 ACCEPTANCE — alias only.

Thin suite entry for public output-contract shape checks. Final acceptance for
CHG-20260724-057 lives in test_narrative_phase2br1_chg057_acceptance_closure.py.
"""

from test_narrative_phase2br1_http_replay_no_repair import (  # noqa: F401
    test_fixture_shapes_match_contract,
    test_schema_generated_from_dto_only,
)
from test_public_provider_boundary import test_public_provider_boundary_script  # noqa: F401
