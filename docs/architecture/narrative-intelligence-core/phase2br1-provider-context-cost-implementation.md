# Phase 2B-R1 Provider Context & Cost Implementation

**Change:** CHG-20260723-046  
**Agent:** U  
**Public branch:** `feature/narrative-phase2br1-provider-context-cost`  
**Private branch:** `feature/phase2br1-provider-context-cost`

## Implemented (public)

| Area | Location |
|------|----------|
| ProviderInputBundle + SourceDataBlock | `private_engine_contract/provider_input.py` |
| Data Transfer Manifest + Consent fingerprint | `private_engine_contract/data_transfer.py` |
| ProviderEstimateResult / CostEstimate | `private_engine_contract/provider_estimate.py` |
| Estimate service + Pricing resolver | `services/whole_book_provider_estimate_service.py` |
| Fake resolver | `services/provider_input_bundle_resolver.py` |
| Consent / Budget guards + Lab preflight | `services/data_transfer_consent_guard.py` |
| Bailian resolved payload + Capturing transport | `services/whole_book_provider_gateway.py` |

## Implemented (private)

| Area | Location |
|------|----------|
| PrivateProviderInputBundleResolver | `provider_input/resolver.py` |
| Message builder (instruction/source isolation) | `provider_input/messages.py` |
| Module context levels / batches / evidence | `context/strategy.py` |
| PrivateStructuredOutputRepairer | `repair/structured_repair.py` |

## Safety boundaries

- Bundle ephemeral: no DB / Artifact / Audit / API body
- Novel text marked `untrusted_source_data=True`; safe_dict omits text
- System instruction isolated from source_data
- Unknown pricing → `None`, never `0`; blocks auto-confirm
- Credential only at execute boundary; boolean presence only in guards
- Capturing transport for tests — no live HTTP in this Change
- Formal Run remains disabled; Private Lab default off
- No Migration / VERSION / gate flips

## Integration handoff

Composition root, router registration, and `main.py` mount remain Integration (CHG-048).
Agent V consumes Manifest / estimate fingerprints on Lab create — does not reassemble messages.
