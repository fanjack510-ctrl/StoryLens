# Whole-Book Contract V1 Invariants

1. **Snapshot immutability:** `status=completed` Snapshot content is immutable; source book changes require a new Snapshot.
2. **Run binds Snapshot:** Every Whole-Book Run must bind a `snapshot_id`; it is immutable for the Run lifetime.
3. **Native does not depend on chapter assets:** `whole_book_native` requires `full_text_snapshot_used=true` and zero chapter/reader-journey asset counts.
4. **Enhanced does not replace full text:** `whole_book_enhanced` may use confirmed assets for enhancement, but still requires full-text Snapshot.
5. **Evidence strict locator:** Locators use Snapshot paragraph Unicode offsets `[start, end)`; quote must equal exact slice; no fuzzy “nearest paragraph” fallback.
6. **Locator failure honesty:** Failed locators are `stale` or `unresolved` — never disguised as successful.
7. **Confirmed not silently overwritten:** Confirmed asset with different `payload_hash` → `create_conflict`; identical → `ignore_identical`.
8. **Fixture ≠ Formal:** Missing `result_origin` must not default to formal; fixture must be explicit.
9. **Overview available requires Evidence:** `availability=available` claims require non-empty `evidence_ids`.
10. **Wire schema identity:** Public and Private wire schema SHA-256 must match for `WIRE_MODEL_NAMES_V1`.
11. **No secrets in safe messages / checkpoints:** API keys, full prompts, full model responses, and full novel text are forbidden in safe/checkpoint payloads.
12. **Contract version freeze:** Breaking changes require `whole_book_contract_v2`.
