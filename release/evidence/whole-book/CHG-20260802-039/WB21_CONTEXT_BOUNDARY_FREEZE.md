# WB-2.1 STRUCTURE AS CONTEXT — BOUNDARY FREEZE

**Status:** FROZEN  
**Decision:**

```
WB-2.1 INPUT ALLOWED：YES（derived context only）
FACT SOURCE：Immutable Book Snapshot / Revision（always）
HARD DEPENDENCY ON STRUCTURE RESULT：NO
```

## Rules

1. **Fact source** remains native book text via Snapshot / CitationCatalog.  
2. StructureStagesResultV2 may be supplied as **optional derived context**（e.g. stage titles/ranges）to help assign functions.  
3. If structure module is **absent / failed / insufficient / canceled**, chapter_functions **MUST still run** when snapshot+catalog are sufficient.  
4. Structure output is **never** SoT for chapter_function assets.  
5. Registry `depends_on: WB-2.1` means **product roadmap ordering / Free module availability sequencing**, not a runtime hard fail when structure payload missing.  
6. Pipeline stage order places `synthesize_chapter_functions` **after** `synthesize_structure_stages` when both run in the same Free run；skip/absent structure does not skip chapter_functions if units remain.  
7. Forbidden：blocking Free chapter_functions solely because structure is planned/failed on another book path.

## Prompt / provider

Providers may receive a compact structure summary block marked `DERIVED_CONTEXT_NOT_FACT`.  
They must not cite structure-only strings as Evidence; Evidence must bind catalog citations to source paragraphs.
