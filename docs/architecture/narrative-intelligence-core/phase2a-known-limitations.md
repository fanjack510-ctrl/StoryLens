# Phase 2A Known Limitations

**Change:** CHG-20260723-035 (post-integration)

1. **Process-local operation idempotency** — pause/resume/cancel/retry dedupe is in-memory; not durable across API restart. Create idempotency is durable via metadata envelope in `validated_output`.

2. **In-process task registry** — `InProcessMockRunTaskRegistry` tracks executor tasks in-process only. No Celery/Redis/worker queue.

3. **Synthetic quota/budget** — counters are mock Lab accounting; not tied to commercial license or real usage billing.

4. **Mock engine only** — `MockWholeBookAnalysisEngine` produces deterministic stub artifacts; no real literary analysis, models, or prompts.

5. **Formal Run still disabled** — `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`; production create path not registered.

6. **No real prompts/models** — executor never calls Model Gateway or Provider; fault injection is test/dev only.

7. **Lab default closed** — `WHOLE_BOOK_MOCK_LAB_ENABLED=false`; requires dev/test env + explicit flag + loopback + marker.

8. **Startup reconcile only** — interrupted runs marked on startup; no silent auto-resume; user must explicitly resume.

9. **No migrations** — metadata in existing JSON columns; no durable op-idempotency table.

10. **Frontend Lab isolated** — not in formal product navigation; production build hides Lab unless explicitly wired.

## Phase 2 inputs

- Durable operation idempotency (if required) needs schema design beyond Phase 2A
- Worker-backed task registry for multi-process deployments
- Formal Run create behind capability gates (future phase)
- Real Engine registration separate from Mock Lab path
