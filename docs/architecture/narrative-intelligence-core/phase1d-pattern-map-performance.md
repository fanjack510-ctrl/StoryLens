# Phase 1D Input — Pattern Map Performance

**Change:** CHG-20260723-014  
**Important:** Pattern nodes are **not** 1:1 with chapters. Book length and graph size are independent.

---

## 1. Scale model

| Dimension | Meaning for Pattern Map |
|-----------|-------------------------|
| 100 / 500 / 1000 chapters | Affects Evidence lookup & reading jump cost, **not** automatic node count |
| ~40 main nodes | Default first paint (collapsed policy) |
| ~80 expanded nodes | Interactive expansion budget for v1 |
| ~200 relations | Edge overlay budget (tree edges + cross edges) |
| Large Evidence sets | **Detail pane only** — never paint all refs on canvas |

Mock reference (`pattern-map.mock.json`):

- Chapters spanned in sample: 1–120  
- Nodes: 81  
- Default visible: 36  
- Fully expanded: 81  
- Edges: ~99  
- Inline evidence refs: 19 (subset of nodes)

---

## 2. Scenario assessment

### 2.1 Chapter count (100 / 500 / 1000)

| Concern | 100 ch | 500 ch | 1000 ch |
|---------|--------|--------|---------|
| Map first paint | Unaffected if node budget fixed | Same | Same |
| Evidence jump | Existing chapter list already range-paginated (`CHAPTER_RANGE_SIZE=100`) | OK with ranges | OK; avoid loading all paragraph bodies |
| Snapshot hash checks | O(paragraph) backend concern | Needs Agent A services | Same |
| Export | Map export cost tied to **visible SVG nodes**, not chapter count | Same | Same |

**Conclusion:** Long books are safe for the map **if** graph cardinality stays bounded and Evidence stays lazy.

### 2.2 Graph cardinality (40 / 80 / 200)

| Operation | ~40 nodes | ~80 nodes | ~200 edges |
|-----------|-----------|-----------|------------|
| First paint | Comfortable (spike) | Comfortable | Draw tree edges always; defer cross-edge overlay |
| Zoom / pan | Transform on `<g>` — cheap | Cheap | Same |
| Collapse / expand | Relayout visible subset | Relayout OK | Hide edges to collapsed subtrees |
| Search | Linear scan of node titles OK through hundreds | OK | Index later if >1k nodes |
| Layout | O(n) tree walk | OK | Cross-edge routing may need queue/idle |
| Virtualization | Not required at 80 | Not required | Consider if >300 visible DOM nodes |
| Memory | Negligible vs chapter text cache | Negligible | Keep Evidence out of map state |
| Export | Rasterize visible SVG | OK | Cap pixel size / scale |

Spike Vitest validates 36→81 expand path and layout id uniqueness (jsdom; not GPU timing).

---

## 3. Performance rules for v1

1. **Default collapse** so first paint ≤ ~40 nodes.  
2. **Lazy Evidence** — counts on nodes; refs fetched for selection only.  
3. **Client layout** of visible nodes only; do not layout collapsed subtrees.  
4. **Cross edges optional layer** — enable after tree is stable.  
5. **No WebGL** in v1.  
6. **No full-book paragraph preload** when opening the map.  
7. If visible nodes exceed ~300, introduce windowing or canvas; until then SVG is enough.

---

## 4. Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Treating every chapter as a node | High (product error) | Contract forbids; tests assert span > node count |
| Painting all Evidence on canvas | High | Detail pane only |
| Installing heavy graph lib prematurely | Medium | Technology options: Option A first |
| Hash mismatch after book edit | Medium | Carry `paragraphContentHash`; gate when snapshot services ready |
| MiniMap for 1000-chapter mental model | Low | MiniMap shows **nodes**, not chapters |

---

## 5. Performance ceiling (guidance)

| Ceiling | Guidance |
|---------|----------|
| Soft v1 interactive | ≤ 100 visible nodes, ≤ 250 edges |
| Hard rethink threshold | > 300 visible DOM nodes or > 1000 edges with full overlay |
| Export | Max dimension clamp (follow Journey export lessons); prefer current viewport export first |

---

## 6. Test evidence (directed)

Commands:

```bash
cd apps/desktop
npm run typecheck
npx vitest run src/features/narrativePattern
```

Covered:

- Mock schema + scale (30–40 default / ≥70 expanded)  
- Collapse / expand / search ancestor expansion  
- Prototype render 40→80, theme toggle, zoom keyboard  
- Evidence deep-link param construction  

Not covered (out of scope): full desktop e2e, Windows installer, production build.
