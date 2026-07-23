# Phase 2B Engine Manifest & Loader

## PrivateWholeBookEngineManifest fields

`manifest_schema`, `manifest_version`, `engine_id`, `engine_version`, `protocol_version`, `implementation_kind`, `private`, `signed`, `signature_algorithm`, `package_hash`, `supported_modes`, `supported_modules`, `supported_languages`, `supported_provider_kinds`, `minimum_app_version`, `maximum_app_version`, `checkpoint_versions`, `result_schema_versions`, `evidence_schema_versions`, `health_capabilities`, `build_id`, `created_at`.

### implementation_kind

`local_private_sidecar` | `local_private_package` | `remote_private_service` | `hybrid_private_engine` | `mock`

## Manifest load rules (10)

1. Formal engine: `private=true`
2. Mock: `private=false` and `non_production=true`
3. `engine_id` / `engine_version` participate in configuration fingerprint
4. Manifest contains no prompt body
5. Manifest contains no credential
6. Signature verification failure → do not load
7. App version incompatible → do not load
8. Unknown protocol version → do not load
9. Production must not degrade to Mock
10. Manifest failure must not silently select another engine

## PrivateWholeBookEngineLoader methods

`discover()` · `inspect_manifest(...)` · `verify_package(...)` · `load(...)` · `unload(...)` · `health_check(...)` · `resolve_compatible_engine(...)` · `list_available_engines(...)`

## Loader rules (10)

1. Does not parse License
2. Capability decision happens before Loader
3. Handles availability/compatibility only
4. No direct ORM access
5. Does not read novel body
6. Does not log prompts
7. Does not log credentials
8. Production does not load unsigned private engines
9. Tests may use Fake Signed Engine
10. Mock Engine remains a separate implementation

Phase 2B-P: Protocol + Fake Loader + fixtures only — no real private binary load.
