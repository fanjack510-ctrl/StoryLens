# StoryLens 1.3.3 Final Release Evidence

Date: 2026-08-25  
Change: `CHG-20260825-014`

## Release outcome

StoryLens 1.3.3 fixes every Pro purchase entry that previously relied on
`window.open` or `target=_blank` inside the Tauri WebView. The desktop build now
validates the HTTPS address and asks Windows to open it with the system default
browser. Missing configuration and browser launch failures are reported as
different user-facing errors.

## Verification

- Pro purchase and entitlement targeted tests: 34 passed.
- TypeScript typecheck, Rust `cargo check`, frontend production build and project
  scaffold checks: passed.
- Windows NSIS release build and artifact gates: passed.
- Release smoke tests: 14 passed.
- Packaged sidecar isolated startup: healthy; built-in material seed contains
  798 cards and no local books.
- Process cleanup: no residual sidecar PID.
- `npm audit --omit=dev`: 0 production vulnerabilities.
- Diff-only API credential, updater private-key and build-machine path scan from
  v1.3.2: 0 matches.
- License release configuration: production public key and Afdian product URL
  valid; no private key tracked.

## Artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `StoryLens_1.3.3_x64-setup.exe` | 46,092,713 | `2cfabf001aa23278a9ca1e6f09b14bdd1bfaf139bcac0b32a48a42a36ed4e207` |
| `storylens-api.exe` | 43,010,915 | `6b8524de7f5358ed8a5d241fa03c6e16e99e37945aa14dd433f9c646d4e2b9c7` |

Updater signature artifacts were not generated because no updater signing
private key was supplied to the build environment. The standalone NSIS
installer is the published artifact.
