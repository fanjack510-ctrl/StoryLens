# Phase 1A Snapshot ↔ Run Stage End-to-End

## Call chain (production default)

```text
RunScopeService
  → SnapshotValidationGateway (Protocol)
    → SnapshotValidationGatewayImpl (= BookSnapshotServiceImpl)
      → BookSnapshotRepositoryImpl / ContentHashServiceImpl
```

`RunStageService(session)` injects the real gateway when none is provided.  
`StubSnapshotValidationGateway` is test-only (not production package export).

## Book Hash Contract

```python
@dataclass(frozen=True)
class BookHashChapterInput:
    chapter_order: int
    title: str
    content_hash: str

def calculate_book_content_hash(chapters: Sequence[BookHashChapterInput]) -> str:
    ...
```

Record format: `{order}:{title_len}:{title}:{content_hash}` joined by LF, then SHA-256.  
Title / order / body hash changes all alter the book digest. Body canonicalization remains CRLF→LF only.

## Snapshot errors

| Field | Role |
|-------|------|
| `source_fingerprint` | Source file fingerprint only |
| `error_code` | FAILED / INVALID diagnostic code |
| `error_message` | Short sanitized message (no full user body) |

COMPLETED snapshots clear error fields. Rebuild does not pollute fingerprint.

## Scope / Stage

- BOOK scope requires COMPLETED snapshot via gateway
- CHAPTER scope does not require snapshot
- Stage matrix: pause/resume; interrupted ≠ failed; failed requires retry; completed not re-run

## Sidecar restart (`mark_interrupted_runs_failed`)

| Run kind | Behavior |
|----------|----------|
| Has `analysis_run_stages` and active staged run | running stages → `interrupted`; run → `interrupted`; checkpoints kept |
| Legacy / no stage rows | prior `failed` semantics for running/queued |

Interrupted runs are **not** auto-resumed and do **not** call models.
