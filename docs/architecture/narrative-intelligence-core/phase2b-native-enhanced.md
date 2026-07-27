# Phase 2B Native vs Enhanced

## whole_book_native

- Depends on completed Snapshot only
- May use Context Pipeline derived intermediates
- Does not require prior chapter analysis assets

## whole_book_enhanced

- Snapshot remains the first fact source
- May read existing Scene / Reader Journey / chapter analysis assets
- Aux data must bind the same book
- Snapshot mismatch → mark `stale`
- Missing aux data → allow degrade; write `warnings` + coverage

## Enhanced assets must not

- Override original text
- Replace Evidence
- Bypass Snapshot hash
- Be treated as default ground truth
