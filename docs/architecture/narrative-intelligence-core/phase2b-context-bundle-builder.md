# Phase 2B Context Bundle Builder

## WholeBookContextBundleBuilder

Inputs: Snapshot · Module Execution Spec(s) · Provider Context Limit · Quality Profile · Budget Policy · Source Language · Analysis Mode

Output: `WholeBookContextBundle`

## Bundle fields

schema / schema_version · snapshot hash · chapter hashes · paragraph hashes · context unit refs · requested/resolved modules · pipeline version · configuration fingerprint · token/character estimate · coverage · warnings · mode · bundle_hash

## Rules

1. Does not default-carry full novel body.
2. Same inputs → same `configuration_fingerprint` and `bundle_hash`.
3. Different Snapshots never share bundles.
4. `validate_context_bundle` must pass before downstream execution.
5. Cache key includes snapshot hash, pipeline version, module spec versions, quality profile, configuration fingerprint.
