# Phase 2B-R Private Repository Boundary

**Change:** CHG-20260723-041  
**Planned private root:** `D:\Dstorylens-private-engine`  
**Audit time:** 2026-07-24

## Existence check

| Path | Result |
|------|--------|
| `D:\Dstorylens-private-engine` | **Does not exist** |
| Action this phase | Plan only — do **not** `git init`, do not create Prompt bodies, do not write algorithm code |
| If later found populated | Audit only; never overwrite/delete/modify without explicit user instruction |

## Protection model (honest)

Client code **cannot** be guaranteed non-decompilable. Obfuscation ≠ security.

Phase-1 closed-source protection relies on:

1. Independent private Git repository  
2. No formal Prompts/algorithms committed to public `D:\Dstorylens`  
3. Manifest + Protocol isolation (`storylens.private_engine.v1`)  
4. Later signed private Sidecar  
5. Release builds exclude private source trees  
6. Optional cloud mode for highest-value strategies  

## Public repo (`D:\Dstorylens`) may keep

- Protocol / DTO / Manifest schemas  
- Loader + signature **verify interface**  
- Gateway Protocols + public adapters  
- Context / Evidence **generic** foundations already in Phase 2B  
- Candidate Persistence Adapter (public side)  
- API / Lab adapters + safety gates  
- Fake / Mock implementations  
- Contract + integration tests  

Primary public contract tree: `apps/api/app/narrative_core/private_engine_contract/`  
FE types only: `apps/desktop/src/features/wholeBook/privateEngineContracts/`

## Private repo (`D:\Dstorylens-private-engine`) will own

| Concern | Notes |
|---------|-------|
| Formal Prompt Pack bodies | System/module templates, examples, repair rules |
| Formal four-module Runners | Algorithms, scoring, conflict heuristics |
| Proprietary context orchestration | Beyond public Context Bundle builder |
| Proprietary Evidence selection | Beyond public validators |
| Output repair algorithms | JSON/schema repair policies |
| Provider routing strategies | Map QualityProfile → Model Route privately |
| Private evaluation rules / indices | Not full copyrighted novels |
| Private Engine entrypoints | Package `__main__` / sidecar entry later |

## Topology

| Stage | Choice |
|-------|--------|
| 2B-R development | Private Python package imported/loaded via public Manifest Loader paths (dev-only); Private Lab |
| 2F release | Signed private Sidecar and/or remote private service; public install lacks private `.py` sources |

Public App never imports private module source by relative path inside the public tree. Discovery goes through Manifest → Loader → Runtime Adapter.

## Leak risk paths in public tree (monitor)

| Path | Risk | Status at 737617f |
|------|------|-------------------|
| `private_engine_contract/` | Must stay Protocol/DTO/Fake only | OK — no formal Prompt bodies |
| `services/fake_*.py`, `Fake*Runner` | Synthetic only | OK |
| `apps/prompts/` (legacy chapter prompts) | Existing chapter pipeline — **not** whole-book formal packs; do not add whole-book packs here | Keep isolated |
| `scripts/run_*.py` real canaries | Chapter/Qwen ops scripts — not whole-book private engine | Do not reuse as whole-book Prompt Pack store |
| Packaging (`build_sidecar.ps1`) | Builds **public** FastAPI sidecar today | Must not bundle private engine sources in 2B-R |

## Agent S bootstrap (next Change, not this one)

When CHG-042 starts and directory is still absent:

1. Create `D:\Dstorylens-private-engine` as new private Git repo (user-approved)  
2. Add README + package skeleton + `.gitignore` (no Prompt bodies yet until pack authoring task)  
3. Record private remote as non-public  

If directory already exists at Agent S start: audit Git status only; do not wipe.
