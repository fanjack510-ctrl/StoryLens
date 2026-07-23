/**
 * Phase 1D Agent J — Whole Book Preflight / Run UX prototype.
 *
 * Isolated under features/wholeBook/runUx/.
 * Do NOT register in product main navigation.
 * Do NOT open real Run creation or call models.
 */

export { WholeBookPreflightView } from "./components/WholeBookPreflightView";
export { WholeBookModeSelector } from "./components/WholeBookModeSelector";
export { WholeBookModuleSelector } from "./components/WholeBookModuleSelector";
export { WholeBookStagePlanPreview } from "./components/WholeBookStagePlanPreview";
export { WholeBookRunProgressView } from "./components/WholeBookRunProgressView";
export { WholeBookStageProgressList } from "./components/WholeBookStageProgressList";
export { WholeBookRunActionBar } from "./components/WholeBookRunActionBar";
export { WholeBookPartialResultNotice } from "./components/WholeBookPartialResultNotice";
export { WholeBookBlockingReasonsPanel } from "./components/WholeBookBlockingReasonsPanel";
export { WholeBookRunUxLabPage } from "./pages/WholeBookRunUxLabPage";
export {
  wholeBookRunUxIsolatedRoute,
  createWholeBookRunUxIsolatedRoutes,
  WHOLE_BOOK_RUN_UX_LAB_PATH,
} from "./routes/isolatedRoute";
export {
  wholeBookPreflightClient,
  PreflightClientError,
  RUN_CREATE_ENABLED_IN_CLIENT,
  WHOLE_BOOK_PREFLIGHT_PATH,
  WHOLE_BOOK_RUN_CREATE_PATH,
} from "./preflightClient";
export { mockRunActionAdapter, applyMockRunAction } from "./mockRunActionAdapter";
export {
  mapPhase1cPreflightToPageModel,
  failClosedPreflightModel,
} from "./preflightMapper";
