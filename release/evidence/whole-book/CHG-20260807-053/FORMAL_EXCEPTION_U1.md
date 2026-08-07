# FORMAL EXCEPTION — EXC-V120-U1-PHASE2BR1-LAB-001

EXCEPTION：  
EXC-V120-U1-PHASE2BR1-LAB-001

APPROVED：  
YES

APPROVED BY：  
Product Owner

APPROVED AT：  
2026-08-07

CHANGE CONTEXT：  
CHG-20260807-053 / WB-2.2.3-V120-L3-PROVIDER closeout of WB-2.2.2 gate

## Classification

LAB_DEBT

## Scope（ONLY）

The **11** Public pytest failures identified in CHG-20260805-052 full suite:

1. `test_narrative_phase2br1_chg057_acceptance_closure.py::test_ac_router_create_scenario_a_valid_flat_no_repair`
2. `…::test_ac_router_create_scenario_b_envelope_one_repair`
3. `…::test_ac_router_create_scenario_c_repair_still_fails`
4. `…::test_ac_model_invocation_authority_is_stage_provider_attempt`
5. `test_narrative_phase2br1_live_engine_provenance.py::test_provider_attempt_checkpoint_written_before_live_assert_fails`
6. `test_narrative_phase2br1_live_network_gate.py::test_authorized_live_uses_injected_transport_once`
7. `…::test_request_dry_run_reaches_adapter_and_matches_gateway`
8. `test_narrative_phase2br1_live_transport_persistence.py::test_live_fake_http_once_not_stub_tokens`
9. `test_narrative_phase2br1_provider_result_binding.py::test_live_executor_binds_provider_response_not_fake`
10. `…::test_empty_structured_fails_live`
11. `test_narrative_phase2br_private_runtime.py::test_private_lab_router_mount_and_dry_create`

## Explicit policy

- Not part of V1.2.0 Free formal product main chain
- Do **not** delete tests
- Do **not** xfail
- Do **not** fake PASS
- Do **not** change Lab product contracts to clear the count
- Do **not** count toward V1.2.0 Free Release Blocking Gate
- Follow-up：Phase2BR1 Lab independent track

## Preserved suite numbers（must not be rewritten）

Public full pytest (CHG-052)：  
**11 failed** / 2184 passed / 54 skipped / 0 errors

Release judgment：

| Field | Value |
|---|---|
| FREE PRODUCT RELEASE BLOCKERS | **0**（after this exception） |
| LAB DEBT | **11** |

## DOES NOT COVER

- Free 正式主链
- Provider L3（WB-2.2.3）
- Release tooling
- Security
- Migration
- Desktop
- Installer
- Any **new** failure after this exception

Any new failure must be classified independently and defaults to blocking if UNKNOWN.
