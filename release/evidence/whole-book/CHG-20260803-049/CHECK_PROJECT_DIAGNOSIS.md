CHECK_PROJECT — CHG-20260803-049
Result: FAIL (not TIMEOUT)
Duration (instrumented re-run): ~143s (CHECK_EXIT=1)
Failure step: change_registry.py check (after version_manager.py check PASSED)
version_manager: PASS (1.2.0)
Historical TIMEOUT diagnosis: prior hangs attributed to change_registry duration / full-tree *.gguf rglob; this HEAD has 0 *.gguf and completes with FAIL at registry gate (~2.5 min), not hang.
Raw: CHECK_PROJECT.txt, CHECK_PROJECT_RAW.txt, CHECK_PROJECT_RERUN.txt
