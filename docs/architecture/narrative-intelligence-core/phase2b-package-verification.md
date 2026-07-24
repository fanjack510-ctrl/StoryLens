# Phase 2B Package Verification

Public interfaces:

- `PrivateEnginePackageVerifier`
- `PromptPackPackageVerifier`
- `DeterministicFakeSignatureVerifier` (test-only; **not** release-grade)

Methods: `verify_manifest` · `verify_package_hash` · `verify_signature` · `verify_compatibility`

## Guarantees

- Production rejects unsigned private packages and Fake/Mock engines
- Invalid signature / hash / protocol / app version / Prompt Pack incompat → stable `PrivateEngineErrorCode`
- No automatic Mock fallback
- Test public key fixture only (`TEST_PUBLIC_KEY_FIXTURE`); no private keys stored
- Does not modify Tauri Updater signing

Formal algorithm remains described by Manifest `signature_algorithm` fields for later phases.
