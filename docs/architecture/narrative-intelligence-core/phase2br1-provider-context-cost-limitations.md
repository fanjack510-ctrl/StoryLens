# Phase 2B-R1 Provider Context & Cost Limitations

**Change:** CHG-20260723-046

1. No live Provider HTTP in this Change — Capturing/Fake transport only.
2. Formal `POST /whole-book-runs` remains disabled.
3. Private Lab remains default-off; no permanent enable.
4. No AnalysisRun / Candidate / Result writes (Agent V / Integration).
5. No router registration or `main.py` wiring (Integration).
6. Generic token heuristic used when provider tokenizer unavailable.
7. Bailian live HTTP transport exists behind probe gate but is not exercised here.
8. Formal Prompt bodies stay private; public Fake uses synthetic short text.
9. Cancel marks refs for transport/gateway; in-flight HTTP abort still Integration+U follow-up when live.
10. Estimate vs actual cost separation is ready; actual usage recording on Lab Run is Agent V.
