# Phase 2B Credential Boundary

## Surfaces

- `ProviderCredentialResolver` Protocol
- `NoCredentialFakeResolver` (Fake path; no real Credential Service)
- `ExistingCredentialServiceAdapter` skeleton over existing `CredentialStore`

## Hard rules

1. Credentials resolve only inside Gateway execute boundary
2. Never enter Execution Request / Artifact / Audit / logs / exception messages
3. Fake Provider does not call real Credential Service
4. Existing user API Key storage unchanged
5. Tests assert serialization has no credential fields
