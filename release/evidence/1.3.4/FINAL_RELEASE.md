# StoryLens 1.3.4 Final Release Evidence

Date: 2026-08-26  
Change: `CHG-20260825-015`

## Release outcome

StoryLens 1.3.4 fixes Pro PDF buttons that appeared to do nothing in the
installed desktop application. The WebView no longer performs the final handoff
through an HTML download anchor. All five PDF products now pass the rendered
bytes to a native Tauri command, save them in the system Downloads directory,
avoid overwriting existing files, and show the exact saved path.

## Verification

- PDF export targeted Vitest suites: 27 passed.
- TypeScript typecheck, Rust `cargo check`, project scaffold checks and frontend
  production build: passed.
- Windows NSIS release build and artifact gates: passed.
- Release smoke tests: 14 passed.
- Packaged sidecar isolated startup: healthy; built-in material seed contains
  798 cards and no local books.
- Process cleanup: no residual sidecar PID.
- `npm audit --omit=dev`: 0 production vulnerabilities.
- Diff-only API credential, updater private-key and build-machine user-path scan
  from v1.3.3: 0 matches.
- License release configuration: production public key and Afdian product URL
  valid; no private key tracked.

## Artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `StoryLens_1.3.4_x64-setup.exe` | 46,101,824 | `8c7e3c926fc1e64ea82aa9a36de65ab56f1e81b67c7f7e799323ea0e1ce0e36f` |
| `storylens-api.exe` | 43,010,778 | `bf813ef48c2848bdda557f9a8f9070edb1bf8f1cc7006db2a3a407d436e38515` |

Updater signature artifacts were not generated because no updater signing
private key was supplied to the build environment. The standalone NSIS
installer is the published artifact.
