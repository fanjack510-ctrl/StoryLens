# Phase 2B Data Handling & Privacy

## WholeBookDataHandlingPolicy fields

`execution_location`, `provider_kind`, `sends_source_text`, `sends_derived_text`, `stores_provider_content`, `retention_policy`, `user_consent_required`, `redaction_policy`, `offline_supported`, `data_region`, `policy_version`

### execution_location

`local` | `cloud` | `hybrid`

## Consent & handling rules

1. Default: do not collect user books
2. Uploading full body requires explicit user consent
3. Local Engine ≠ permission for arbitrary network transfer
4. Cloud Provider use shows data-transfer notice first
5. Credentials never enter private Engine DTOs
6. Logs do not record full text
7. Audit does not record full text
8. Artifacts do not record full text
9. Provider response raw text handled per policy
10. Collecting analysis results later needs separate consent
