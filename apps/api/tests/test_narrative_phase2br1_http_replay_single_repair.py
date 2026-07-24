"""NOT COUNTED FOR CHG-057 ACCEPTANCE — alias only.

Thin re-export of HTTP replay single-repair coverage from
test_narrative_phase2br1_http_replay_no_repair.py. Final acceptance for
CHG-20260724-057 lives in test_narrative_phase2br1_chg057_acceptance_closure.py.
"""

from test_narrative_phase2br1_http_replay_no_repair import (  # noqa: F401
    test_http_replay_single_repair,
)
