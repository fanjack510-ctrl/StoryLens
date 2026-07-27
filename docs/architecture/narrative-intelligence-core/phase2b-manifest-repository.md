# Phase 2B Manifest Repository

`PrivateEngineManifestRepository` reads Manifest JSON under a bounded root directory.

## Methods

`discover_manifests` · `load_manifest` · `inspect_manifest` · `list_manifests` · `find_by_engine_id` · `find_compatible`

## Rules enforced

1. Manifest-only (no private binary load)
2. No novel body scan
3. Schema/version validation (`storylens.private_engine.manifest` / `1.0.0`)
4. Unique `(engine_id, engine_version)`
5. `package_hash` format (`sha256:`… or non-prod `fake-`/`mock-` prefixes)
6. Path traversal / outside-root refs rejected
7. Production skips Fake/Mock/non_production manifests
8. Compatible selection strategy: signed first → higher version → engine_id

Fixtures use temporary directories via `write_fake_engine_package`.
