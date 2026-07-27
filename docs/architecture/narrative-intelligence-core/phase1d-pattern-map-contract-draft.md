# Phase 1D Input — Pattern Map Contract Draft

**Change:** CHG-20260723-014  
**Status:** Frontend Contract draft only — **not** a database schema  
**Schema version:** `pattern-map-draft-1`  
**TypeScript source of truth:** `apps/desktop/src/features/narrativePattern/contracts/patternMap.draft.ts`

---

## 1. Design principles

1. Every node/edge must be able to cite `relatedAssetIds` + Evidence refs (Asset/Relation/Evidence triangle).  
2. Hierarchy (`parentId`) is a **projection**, not the only truth — cross edges encode setup/payoff, foreshadow, parallel, growth.  
3. **Never** assume 1 chapter = 1 node. Nodes carry `startChapterId` / `endChapterId` spans.  
4. Evidence payloads stay out of the map envelope; detail pane loads by node/edge id.  
5. User confirmation (`userStatus`) is first-class — map is editable judgment, not raw model dump.

---

## 2. DTO catalog

### NarrativePatternMapDto

| Field | Type | Notes |
|-------|------|-------|
| schemaVersion | `"pattern-map-draft-1"` | Breaking changes bump string |
| bookId | number | Workspace book |
| bookSnapshotId | string | Immutable text basis |
| title | string | Display title |
| generatedAt | ISO string | Analysis timestamp |
| defaultFilter | PatternMapFilterDto | Initial facet |
| defaultViewport | PatternMapViewportDto | Initial camera/selection |
| nodes | PatternMapNodeDto[] | Full node set for current projection |
| edges | PatternMapEdgeDto[] | Hierarchical + cross relations |
| evidenceByNodeId? | map | **Mock/prototype only**; production omits |

### PatternMapNodeDto

| Field | Required | Notes |
|-------|----------|-------|
| id | yes | Stable within snapshot analysis |
| parentId | yes (nullable) | Tree overlay |
| title / summary | yes | UI copy |
| nodeType | yes | `book_root` \| `structure_stage` \| `storyline` \| `character_arc` \| `beat` \| `turning_point` \| `payoff_cluster` \| `supporting` |
| depth / orderIndex | yes | Layout hints |
| importance / confidence | yes | 0–1 floats |
| startChapterId / endChapterId | yes (nullable) | Span, not 1:1 |
| relatedCharacterIds / relatedStorylineIds / relatedAssetIds | yes | Traceability |
| evidenceCount / childCount | yes | Counts only |
| collapsedByDefault | yes | First-paint policy |
| userStatus | yes | `unreviewed` \| `confirmed` \| `disputed` \| `ignored` |

### PatternMapEdgeDto

| Field | Notes |
|-------|-------|
| id | Stable edge id |
| sourceNodeId / targetNodeId | Directed |
| relationType | `parent_child` \| `setup_payoff` \| `parallel` \| `foreshadow` \| `character_growth` \| `storyline_cross` |
| confidence | 0–1 |
| relatedAssetIds | Relation/Asset ids |
| evidenceCount | Count only |
| label | Optional short label |

### PatternMapEvidenceRefDto

| Field | Notes |
|-------|-------|
| bookSnapshotId | Snapshot binding |
| chapterId | Existing chapter id |
| sceneId | Nullable until scene resolved |
| paragraphId | Existing paragraph id string |
| paragraphContentHash | SHA-256 hex of canonical paragraph text |
| label | Human-readable reason for citation |

### PatternMapFilterDto

`mode`: `structure_stage` | `storyline` | `character_growth` | `all`  
Plus id allow-lists, `minConfidence`, `includeDisputed`, `searchQuery`.

### PatternMapViewportDto

`scale`, `translateX`, `translateY`, `focusedNodeId`, `selectedNodeId`.

---

## 3. Node / edge relationship model

```text
book_root
  ├── structure_stage*     (spine)
  │     └── beat | turning_point | payoff_cluster | supporting
  ├── storyline*
  │     └── beat*
  └── character_arc*
        └── beat*  (+ character_growth edges)
```

Cross edges (non-tree):

- `setup_payoff` — promise → reveal  
- `foreshadow` — plant → payoff  
- `parallel` — concurrent pressure  
- `storyline_cross` — line A affects line B  
- `character_growth` — arc progression (may duplicate parent_child intentionally for filter mode)

v1 UI may render tree edges always and cross edges as optional overlays.

---

## 4. Evidence jump Contract

Frontend helper: `evidenceDeepLink.ts`

```text
/books/{bookId}?chapter={id}&scene={id?}&paragraph={id}&view=reading
  &bookSnapshotId={id}&paragraphContentHash={hash}
```

| Step | Owner | Status |
|------|-------|--------|
| Resolve chapter | existing workspace | Ready |
| Resolve scene + paragraph scroll | Reader Journey / StructuredChapterTextPane | Ready |
| Validate hash vs snapshot paragraph | Agent A + future UI gate | **Not ready** |

---

## 5. Theme Contract

Map chrome must consume StoryLens tokens (`--color-*`) and honor `data-theme=light|dark`.  
Spike validates local override without mutating global `uiStore` (product wiring can bind later).

---

## 6. First-version limits (frontend Contract)

1. Single projection payload per request (filter server-side or client-side TBD).  
2. No embedded paragraph text in map DTO.  
3. No layout coordinates from backend (client lays out).  
4. No real-time collaboration fields.  
5. `evidenceByNodeId` is non-production.

---

## 7. Downstream database Contract inputs

Future Integration / DB Contract should consider tables/collections for:

1. `narrative_pattern_maps` — book_snapshot_id, schema_version, generated_at, status  
2. `narrative_pattern_nodes` — fields mirroring PatternMapNodeDto + analysis_run_id  
3. `narrative_pattern_edges` — fields mirroring PatternMapEdgeDto  
4. `narrative_pattern_evidence` — node/edge FK + PatternMapEvidenceRefDto columns  
5. `narrative_pattern_user_state` — per-user `userStatus`, collapse preferences, viewport  

**Do not** create these in Agent C. Hash columns must align with Agent A `content_hash` canonicalization rules.

---

## 8. Mock reference

`apps/desktop/src/features/narrativePattern/mocks/pattern-map.mock.json`

- Depths 0–3  
- Default visible ≈ 36  
- Fully expanded ≈ 81  
- Includes stages, storylines, character arcs, evidence, collapse, confidence, userStatus  
- Generic fiction only  

Validated by `patternMapMock.test.ts` + `patternMap.guards.ts`.
