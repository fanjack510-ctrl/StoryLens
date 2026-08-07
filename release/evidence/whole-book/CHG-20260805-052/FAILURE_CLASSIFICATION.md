# FAILURE_CLASSIFICATION — CHG-20260805-052 (post-integration)

Parent triage：CHG-20260803-049 / Agent1 U1 conclusion.

## Public full pytest remaining

**11 failed**, 2184 passed, 54 skipped, **0 collection errors**, 919s.

| # | Node | Class | Notes |
|---|---|---|---|
| 1 | `test_narrative_phase2br1_chg057_acceptance_closure.py::test_ac_router_create_scenario_a_valid_flat_no_repair` | LAB_DEBT | U1 chg057 / private lab |
| 2 | `…::test_ac_router_create_scenario_b_envelope_one_repair` | LAB_DEBT | U1 |
| 3 | `…::test_ac_router_create_scenario_c_repair_still_fails` | LAB_DEBT | U1 |
| 4 | `…::test_ac_model_invocation_authority_is_stage_provider_attempt` | LAB_DEBT | U1 |
| 5 | `test_narrative_phase2br1_live_engine_provenance.py::test_provider_attempt_checkpoint_written_before_live_assert_fails` | LAB_DEBT | U1 live |
| 6 | `test_narrative_phase2br1_live_network_gate.py::test_authorized_live_uses_injected_transport_once` | LAB_DEBT | U1 live/transport |
| 7 | `…::test_request_dry_run_reaches_adapter_and_matches_gateway` | LAB_DEBT | U1 |
| 8 | `test_narrative_phase2br1_live_transport_persistence.py::test_live_fake_http_once_not_stub_tokens` | LAB_DEBT | U1 |
| 9 | `test_narrative_phase2br1_provider_result_binding.py::test_live_executor_binds_provider_response_not_fake` | LAB_DEBT | U1 provider-binding |
| 10 | `…::test_empty_structured_fails_live` | LAB_DEBT | U1 |
| 11 | `test_narrative_phase2br_private_runtime.py::test_private_lab_router_mount_and_dry_create` | LAB_DEBT | private lab router; default off |

## Free entry loading check

`is_private_engine_lab_enabled_from_env(environ={})` → **False**

Therefore U1 remains **LAB_DEBT**, not RELEASE_BLOCKER product defect on Free main chain.

Numeric release gate still requires 0 failed **or** formal exception / quarantine — **not auto-approved**.

## Deferred (unchanged)

| ID | Item | Class |
|---|---|---|
| X1 | Reader offset highlight enhancement | DEFERRED_NON_BLOCKING |
| X2 | DEV diagnostics fuzzy cleanup | DEFERRED_NON_BLOCKING |

DEFERRED ITEMS AFFECT PRODUCTION CONTRACT：**NO**

## UNKNOWN

(none)
