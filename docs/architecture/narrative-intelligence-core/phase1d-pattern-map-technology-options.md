# Phase 1D Input — Pattern Map Technology Options

**Change:** CHG-20260723-014  
**Rule:** Prefer existing dependencies. **Do not install** new packages in this Change. Final choice by Integration / user.

---

## 1. Current dependency inventory (desktop)

Present runtime deps:

- `react` / `react-dom` 19  
- `react-router-dom` 7  
- `@tanstack/react-query`  
- `zustand`  
- `@tauri-apps/api` (+ process/updater plugins)

**No** graph/visualization packages are installed.

In-repo custom visualization precedents:

- SVG Journey chart (`CanonicalJourneyChart`)  
- PNG export without `html-to-image` (`exportJourneyPng`)

---

## 2. Option comparison (minimum two)

### Option A — Dependency-free SVG tree (recommended for v1)

| | |
|--|--|
| **What** | Hand-rolled hierarchical layout + SVG nodes/edges (spike: `PatternMapPrototype`) |
| **Pros** | Zero new deps; matches Journey SVG/export/theme patterns; full control of Evidence UX; easy Tauri WebView story; small bundle |
| **Cons** | Cross-edge routing / MiniMap / advanced layout need custom work; not ideal for dense force-directed networks |
| **Fits** | Structure map with ~40 default / ~80 expanded nodes, tree-first + optional cross-edge overlay |

### Option B — React Flow / `@xyflow/react`

| | |
|--|--|
| **What** | Popular node graph editor (MiniMap, pan/zoom, custom nodes) |
| **Pros** | Fast MiniMap, controls, interaction polish; large ecosystem |
| **Cons** | New major dependency; editor-oriented (easy to become “mind map”); themeing must be re-skinned to StoryLens tokens; bundle + WebView QA cost |
| **Fits** | Later if product demands free-form node dragging / MiniMap as must-have |

### Option C — Cytoscape.js / `react-cytoscapejs` (not recommended now)

| | |
|--|--|
| **Pros** | Strong DAG / network analytics layouts |
| **Cons** | Heavier; styling less React-native; overkill for hierarchical narrative spine; higher a11y cost |
| **Fits** | Research / dense relation network views — not Structure Map v1 |

### Option D — D3 hierarchy / dagre-d3 (not recommended as primary)

| | |
|--|--|
| **Pros** | Excellent layout math |
| **Cons** | Still a new dependency family; React integration boilerplate; Journey already proves SVG without D3 |

If layout quality becomes the blocker, prefer **adding only a layout lib** (e.g. `dagre` or `elkjs`) behind Option A’s SVG renderer — not replacing the whole renderer.

---

## 3. Recommendation

| Phase | Choice |
|-------|--------|
| **Now (0B spike)** | Option A — validated locally |
| **Product v1** | Option A + reuse Inspector/detail drawer + token theme |
| **Revisit** | Option B only if MiniMap + free drag become acceptance criteria |
| **Avoid for v1** | Cytoscape as primary; ECharts tree as primary (chart semantics ≠ narrative map) |

### Need new dependency?

| Question | Answer |
|----------|--------|
| Required to ship Contract draft / readiness? | **No** |
| Required for v1 at ~80 visible nodes? | **No** (spike OK) |
| Possible later optional add | Layout-only (`dagre`/`elkjs`) or React Flow — **Integration approval required** |

---

## 4. Interaction mapping (spike coverage)

| Requirement | Spike status |
|-------------|--------------|
| Tree layout | Yes |
| Expand / collapse | Yes |
| Zoom + pan | Yes (scale + pointer drag; ctrl/meta wheel) |
| Node selection | Yes |
| Node detail | Yes (side panel) |
| Theme toggle | Yes (local `data-theme`) |
| ~40 default nodes | Yes (mock) |
| ~80 expanded | Yes (mock) |
| Search locate | Yes |
| Keyboard basics | Yes (+/− zoom, Enter toggle, search arrows) |
| MiniMap | No — deferred |
| Cross-edge fancy routing | No — deferred overlay |

---

## 5. Export strategy

Reuse `exportJourneyPng` approach (clone DOM/SVG, inline computed styles, canvas rasterize).  
Do **not** add `html2canvas` / `dom-to-image` unless Journey export is also migrated.

SVG vector export can be a later additive path (serialize SVG node) without new deps.

---

## 6. Decision log (for Integration)

- [ ] Confirm Option A for product v1  
- [ ] If MiniMap required in first shippable Pro surface → reopen Option B  
- [ ] Any new npm dependency requires explicit Change + bundle impact note  
