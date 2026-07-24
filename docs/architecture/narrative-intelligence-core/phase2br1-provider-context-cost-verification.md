# Phase 2B-R1 Provider Context & Cost Verification

**Change:** CHG-20260723-046

## Commands

Public worktree:

```text
D:\Dstorylens\.venv\Scripts\python.exe -m pytest apps/api/tests/test_narrative_phase2br1_provider_context_cost.py -q
D:\Dstorylens\.venv\Scripts\python.exe scripts/check_project.py
D:\Dstorylens\.venv\Scripts\python.exe scripts/version_manager.py check
D:\Dstorylens\.venv\Scripts\python.exe scripts/change_registry.py check
D:\Dstorylens\.venv\Scripts\python.exe scripts/check_capability_keys.py
git diff --check
```

Private worktree:

```text
D:\Dstorylens\.venv\Scripts\python.exe -m pytest tests/test_provider_context_assembly.py -q
```

## Coverage checklist (public test file)

1. Input Bundle  
2. Safe serialization omits text  
3. Instruction / source isolation  
4. Context limit  
5. Manifest  
6. Consent fingerprint  
7. Manifest change invalidates consent  
8. Token estimate ≠ 512/256 placeholder  
9. Output estimate from policy  
10. Cost low/expected/high  
11. Unknown pricing  
12. Retry cost  
13. Budget denied  
14. Daily budget  
15. Cancel blocks retry  
16. Credential not in DTO  
17–18. Credential / messages not in logs  
19–21. Adapter resolved payload + json_object capture  
22. Timeout  
23. Cancel  
24–26. Invalid JSON / repair success / repair reject  
27. Raw response not retained  
28–29. No HTTP / no model  
30–31. Formal Run off / Private Lab default off  
32. No Migration  

## Expected status

CHG-046 → **tested** (max for this Change). Live Smoke remains Integration.
