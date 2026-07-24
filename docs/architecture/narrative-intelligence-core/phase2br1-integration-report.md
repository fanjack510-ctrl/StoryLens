# Phase 2B-R1 Integration Report

## Scope

Merge Agent U (provider context / cost) and Agent V (Private Lab runtime / persistence)
into one development-level live-readiness chain. No real Provider HTTP in Integration CI.

## Composition

- `PrivateWholeBookLiveReadinessRuntime` — public composition root
- `PrivateLab*ServiceAdapter` — V Ports → U services
- Private `compose_private_lab_runtime` — entry + runners + provider_input resolver

## Chain

Preflight → Estimate (Manifest + Token/Cost + Consent/Estimate fingerprints) →
Create (server security) → AnalysisRun/Stages → Provider Payload (Capturing/dry) →
Four modules sequential → Schema/Evidence validation → Phase1B Candidate/Evidence →
Result API

## Gates

- Private Lab default off; Mock Lab default off; formal whole-book create disabled
- Live Probe + allow_network both required for real HTTP; CI never enables Live Probe
- Client booleans (`credential_present` / `budget_ok` / `capability_ok`) are deprecated
  and not authoritative for live create

## Status

CHG-20260723-048 max `tested`. Manual Live Smoke not executed in this Integration.
