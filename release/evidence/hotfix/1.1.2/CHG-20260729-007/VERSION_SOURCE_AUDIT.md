# VERSION_SOURCE_AUDIT — CHG-20260729-007

**Public HEAD at audit (post CHG-006 FF):** `8206a279a8ade58505f20ad3a6ad462a26243dad`  
**Bump tool:** `python scripts/version_manager.py set 1.1.2`

## Classification

### A. Current product authority (updated to 1.1.2)

| Source | Path | Role |
|--------|------|------|
| VERSION | `VERSION` | Single source of truth |
| Desktop package | `apps/desktop/package.json` | npm product version |
| Desktop lock | `apps/desktop/package-lock.json` | lock sync |
| Tauri conf | `apps/desktop/src-tauri/tauri.conf.json` | installer/app metadata |
| Cargo | `apps/desktop/src-tauri/Cargo.toml` + `Cargo.lock` | Rust package |
| API package | `pyproject.toml` | Python package version |
| API runtime | `apps/api/app/__init__.py` (`__version__`) | FastAPI / UI footer injection |

UI footer / desktop build inject `__STORYLENS_APP_VERSION__` from VERSION via Vite (see `apps/desktop/src/lib/appVersion.ts`).

### B. Generated / synced

- `package-lock.json`, `Cargo.lock` — synced by version_manager
- Updater template keeps `{{VERSION}}` placeholder (not literal 1.1.2)

### C. Historical evidence / compatibility (not rewritten)

- `release/evidence/**` mentioning 1.1.1
- `release/notes/StoryLens-1.1.1.md`
- Change records `base_version: 1.1.1`
- Tag `v1.1.1` @ `6f7d88c41f8006176fe77dd92bdb06cf1c6683e3`

### D. Tests

- `apps/desktop/src/lib/appVersion.test.tsx` expects SemVer shape from build inject — no hard-coded 1.1.1 product claim to rewrite

### E. Must not modify

- Git tag `v1.1.1`
- GitHub Release v1.1.1 artifacts
- CHG-042 investigation evidence (not product version)

## Post-bump check

`python scripts/version_manager.py check` → **PASS** for 1.1.2
