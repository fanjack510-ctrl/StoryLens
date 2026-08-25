# StoryLens 1.3.2 Final Release Evidence

Date: 2026-08-25  
Change: `CHG-20260825-013`

## Release outcome

StoryLens 1.3.2 packages the approved material catalog as a sanitized,
Pydantic-validated asset. A clean packaged sidecar imports all 798 cards on
startup without inheriting any build-machine book or SQLite row. Existing
user-owned materials are preserved and equivalent cards are skipped.

## Verification

- Targeted material seed tests: 4 passed.
- Project scaffold and change registry checks: passed.
- Windows release build and artifact gates: passed.
- Release smoke tests: 14 passed.
- Packaged sidecar isolated state: `knowledge_count=798`,
  `imported_knowledge_count=798`, `source_book_count=0`.
- Process cleanup: no residual sidecar PID.
- `npm audit --omit=dev`: 0 production vulnerabilities.
- Diff-only credential, private-key, API-environment and local-path scan from
  v1.3.1: 0 matches; no new sensitive file paths.
- License release configuration: production public key and Afdian product URL
  valid; no private key tracked.

## Artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `StoryLens_1.3.2_x64-setup.exe` | 46,091,822 | `d6d62dfff28421ecd8dbfa148f46d97baa757ade8f6d6ca0134f4cb6db008f16` |
| `storylens-api.exe` | 43,010,755 | `2b7b40b2226d99524d29e6c30b885a02218c75b3517002483ed5a210806f31a9` |
| `storylens_material_seed_v1.json` | 1,084,509 | `e2c84ffce24577853d20b8e5be26e98d3126f543642813b82e1aec8bd8a49093` |

Updater signature artifacts were not generated because no updater signing
private key was supplied to the build environment. The standalone NSIS
installer is the published artifact.
