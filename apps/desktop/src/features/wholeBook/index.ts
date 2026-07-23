/**
 * Phase 1D wholeBook feature barrel — shared isolated prototypes.
 *
 * Do NOT register in product main navigation / AppShell.
 * Lab path constants may exist but must not be wired into product Router.
 */

export * from "./contracts";
export * as runUx from "./runUx";
export * as review from "./review";
export * as structureMap from "./structureMap";

export {
  WHOLE_BOOK_RUN_UX_LAB_PATH,
  createWholeBookRunUxIsolatedRoutes,
} from "./runUx";
