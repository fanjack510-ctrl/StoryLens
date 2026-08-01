# CHG-20260801-031 Layout Root Cause

## Layout root component
`apps/desktop/src/pages/WholeBookFreeProductPage.tsx`  
CSS module: `WholeBookFreeProductPage.module.css`  
Test id: `whole-book-free-product-page`

## Outer shell
`AppShell` (`.app-shell-simplified`) provides left global nav (~200px) + `<main><Outlet/></main>`.
No additional article max-width on `<main>`.

## Root cause
`.wholeBookFreePage` used article-style centering:

```css
max-width: 1200px;
margin: 0 auto;
```

Combined with single-column claim list and auto-fit limits grid, the workbench appeared as a narrow centered column on ≥1920 screens with large left/right gutters inside `<main>`.

## Before metrics (1920×1080, Playwright)
- Product page bounding width ≈ 650 CSS-px under `html { zoom: 0.8 }` (≈812 layout px)
- Claims: 1 column

## After design
| Token | Value |
| --- | --- |
| width | 100% |
| max-width | 1560px (1600px @ ≥1920) |
| padding | clamp(24px, 3vw, 56px) |
| desktop grid | `240px minmax(0, 1fr)` |
| overview cards | 2 columns (≥1440-ish; 1 col ≤1280 band) |
| limits grid | 3 columns desktop; 2 @ ≤1366; 1 @ ≤1050 |
| stack breakpoint | ≤1050px nav above content |

## Not changed
API, prepare routes, DB, Provider, Free/Pro boundaries, Evidence deep link logic, Private engine.
