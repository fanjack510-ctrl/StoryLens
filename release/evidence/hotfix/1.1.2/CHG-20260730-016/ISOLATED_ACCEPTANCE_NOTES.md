# RC.5 Isolated Acceptance Notes

## Install-state (packaged sidecar)
- CONFIG / CWD 6/6 / HEALTH / SECURITY / INSTALLER: PASS
- Formal DB writes: 0
- Real provider calls: 0

## CHG-015 functional fixtures against packaged sidecar (seeded DB reads)
- Scene failure stage: PASS
- Synthesis failure stage: PASS
- Recoverable interrupted current run: PASS

## Scene Wait Gate live confirm on packaged/frozen sidecar
- Smoke Fake is hard-rejected when `is_frozen()` (see chapter_analysis_smoke_fake_transport).
- Confirm+start then hits `Provider已停用` — expected safety gate.
- Wait-gate behaviour covered by: MG-CHG-20260730-015 PASSED, pytest CHG-015, and uvicorn Fake AUTO_PREACCEPTANCE.

## Continue same-run
- Covered by MG C2 + CONTINUE_SAME_RUN_PROOF.json + pytest recoverable current-run.
