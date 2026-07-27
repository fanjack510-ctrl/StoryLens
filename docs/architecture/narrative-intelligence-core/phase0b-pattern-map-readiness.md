# Phase 0B — Narrative Structure Map Readiness

**Change:** CHG-20260723-014  
**Agent:** C  
**Branch / Worktree:** `feature/narrative-pattern-readiness` @ `D:\Dstorylens-wt-pattern-audit`  
**Baseline:** `e983e7279d4c72655334017da114ce572e41b0e0` (Phase 1P)  
**Nature:** Readiness audit + frontend Contract draft + isolated spike. **No** production DB / model / Pro route work.

---

## 1. Product framing (constraints)

Narrative Structure Map must be:

| Must | Must not |
|------|----------|
| Traceable to Narrative Asset / Relation / Evidence | Fixed novel template |
| Switchable by structure stage / storyline / character growth | Generic mind-map |
| Clickable to chapter / scene / paragraph evidence | Free-form model summary graph |

This phase only audits capability and freezes a frontend Contract.

---

## 2. Current visualization baseline

### 2.1 Stack

| Layer | Status |
|-------|--------|
| React 19 + Vite 6 + TypeScript 5.7 | Present (`apps/desktop`) |
| Tauri 2 (`@tauri-apps/api` 2.x) | Present |
| react-router-dom 7 | Present |
| zustand + TanStack Query | Present |
| Chart / graph libraries (React Flow, D3, Cytoscape, ECharts…) | **Absent** |

### 2.2 Reusable capabilities already in product

| Capability | Where | Reuse for Pattern Map? |
|------------|-------|------------------------|
| Custom SVG chart | `CanonicalJourneyChart.tsx` | Yes — SVG + pointer pan patterns |
| Horizontal pan / brush zoom | Journey chart + toolbar | Partial — adapt to 2D pan/zoom |
| Tooltip | Journey hover tooltips | Pattern yes; reuse UX language |
| Detail drawer / Inspector | `inspectorShell.tsx`, Scene detail | **Primary reuse** for node detail |
| Theme light/dark | `appearanceTheme.ts` + `tokens.css` (`data-theme`) | Yes — bind map chrome to tokens |
| Chapter deep link | `chapterNavigation.ts` `?chapter=` | Yes |
| Scene / paragraph deep link | `journeySelectionTransaction.ts` + `StructuredChapterTextPane` `#sync-p-*` | Yes |
| PNG export (no new dep) | `exportJourneyPng.ts` (DOM → canvas → blob) | Reusable pattern for map export later |
| Chapter navigator drawer | `ChapterNavigatorDrawer` | UX reference only |

### 2.3 Missing capabilities

| Capability | Status |
|------------|--------|
| Tree / DAG layout engine | Missing (spike uses hand-rolled tree layout) |
| Relationship network force layout | Missing |
| MiniMap | Missing |
| Node search (graph-wide) | Missing in product; present in spike |
| Collapse / expand hierarchical nodes | Missing in product; present in spike |
| Graph virtualization | Missing |
| Content-hash validated evidence jump | Missing (hash carried in draft link only) |
| Formal Pattern Map route / Pro page | Intentionally absent this phase |

### 2.4 Theme & visual tokens

- SSOT: `storylens.appearance.theme` → `documentElement.dataset.theme` / `.app[data-theme]`
- Tokens: `apps/desktop/src/styles/tokens.css` (brand green palette, light/dark)
- Spike mirrors the same CSS variables locally so it stays theme-compatible without touching AppShell

### 2.5 Evidence → source text feasibility

**Feasible now** for chapter / scene / paragraph navigation using existing query params and scroll helpers.  
**Not feasible yet** for snapshot `paragraphContentHash` integrity gate in UI (depends on Agent A snapshot services + future workspace wiring).

See `lib/evidenceDeepLink.ts` and `CURRENT_EVIDENCE_LOCATE_CAPABILITY`.

### 2.6 Tauri WebView notes

- Current Journey SVG + pointer capture works under Tauri WebView2 (Windows)
- Prefer SVG/DOM over WebGL for v1 (simpler export + theme + a11y)
- Ctrl/Meta + wheel zoom is acceptable; avoid relying on browser-only extensions
- Large SVG export should follow `exportJourneyPng` clone+inline-style approach (already WebView-tested pattern)

---

## 3. Recommended direction (summary)

1. **v1 renderer:** dependency-free SVG tree (spike validated) + reuse Inspector/detail drawer patterns  
2. **Defer** React Flow / Cytoscape until cross-edge density or MiniMap becomes a product requirement  
3. **Evidence:** load refs in detail pane only; jump via existing deep links  
4. **Scale model:** pattern nodes ≠ chapters; default ~40 visible, expand on demand  

Detail comparisons → `phase1d-pattern-map-technology-options.md`  
DTO freeze → `phase1d-pattern-map-contract-draft.md`  
Perf bounds → `phase1d-pattern-map-performance.md`

---

## 4. Deliverables in this Change

| Artifact | Path |
|----------|------|
| Readiness (this doc) | `docs/architecture/narrative-intelligence-core/phase0b-pattern-map-readiness.md` |
| Contract draft | `…/phase1d-pattern-map-contract-draft.md` |
| Tech options | `…/phase1d-pattern-map-technology-options.md` |
| Performance | `…/phase1d-pattern-map-performance.md` |
| DTO + guards | `apps/desktop/src/features/narrativePattern/contracts/` |
| Mock | `apps/desktop/src/features/narrativePattern/mocks/pattern-map.mock.json` |
| Spike | `apps/desktop/src/features/narrativePattern/prototype/` |

---

## 5. Explicit non-goals (enforced)

- No `models.py` / migration / Pattern tables  
- No Narrative Asset creation / model calls / whole-book analysis API  
- No formal nav / Pro page / Capability / VERSION / `unreleased.json` edits  
- No Windows installer / publish / push  

---

## 6. Integration handoff

Integration should:

1. Keep Agent C paths exclusive until merge  
2. Treat DTOs as **frontend Contract input** to a future DB Contract (do not copy 1:1 into ORM)  
3. Decide dependency install only after reviewing technology options doc  
4. Wire routes only in a later Change after Phase 1A snapshot + run/stage land  
