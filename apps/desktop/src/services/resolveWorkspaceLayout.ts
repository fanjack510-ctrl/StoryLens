/**
 * Single decision table for BookRoutePage workspace layout.
 * All branches are mutually exclusive — no parallel ProgressWorkspace + ResultFullPage.
 */

export type WorkspaceActiveTab = "text" | "scene" | "journey";
export type WorkspaceMainState =
  | "idle"
  | "loading"
  | "ready"
  | "pending_generation"
  | "unavailable"
  | "scope_mismatch"
  | "invalid_artifact"
  | "request_error";

export type WorkspaceLayout = {
  activeTab: WorkspaceActiveTab;
  /** URL-compatible shell view for existing CSS/tests. */
  shellView: "reading" | "progress" | "result";
  showNavigationInMain: boolean;
  showProgressContext: boolean;
  mainContentState: WorkspaceMainState;
  /** Dev-facing mode label. */
  workspaceMode: "reading" | "progress" | "scene_result" | "journey_result";
  navigationPaneMode: "hidden" | "chapter_nav";
  contextPaneMode: "hidden" | "progress" | "scene_detail" | "journey_detail";
};

export function mapUrlToActiveTab(args: {
  requestedView: string | null;
  requestedTab: string | null;
  chapterComplete: boolean;
  journeyAvailable: boolean;
  sceneAvailable: boolean;
  userPinnedTab: WorkspaceActiveTab | null;
}): WorkspaceActiveTab {
  const { requestedView, requestedTab, chapterComplete, journeyAvailable, sceneAvailable, userPinnedTab } =
    args;

  if (userPinnedTab) return userPinnedTab;

  if (requestedView === "reading" || requestedView === "progress") return "text";

  if (requestedTab === "reader-journey" || requestedTab === "journey") return "journey";
  if (
    requestedTab === "scene-analysis" ||
    requestedTab === "analysis" ||
    requestedTab === "structure"
  ) {
    return "scene";
  }

  if (requestedView === "result") {
    if (chapterComplete && journeyAvailable) return "journey";
    if (sceneAvailable) return "scene";
    return "scene";
  }

  // Default: text/reading. Never auto-jump to Journey because history exists.
  return "text";
}

export function resolveWorkspaceLayout(args: {
  requestedView: string | null;
  requestedTab: string | null;
  userPinnedTab: WorkspaceActiveTab | null;
  chapterComplete: boolean;
  inFlight: boolean;
  sceneAvailable: boolean;
  journeyAvailable: boolean;
  journeyStatus: string | null | undefined;
  journeyQueryStatus: "idle" | "loading" | "success" | "error";
  journeyIntegrityStatus?: string | null;
  journeyTrusted?: boolean | null;
  scopeMismatch?: boolean;
}): WorkspaceLayout {
  const activeTab = mapUrlToActiveTab({
    requestedView: args.requestedView,
    requestedTab: args.requestedTab,
    chapterComplete: args.chapterComplete,
    journeyAvailable: args.journeyAvailable,
    sceneAvailable: args.sceneAvailable,
    userPinnedTab: args.userPinnedTab,
  });

  const showProgressContext = Boolean(args.inFlight);

  let mainContentState: WorkspaceMainState = "idle";
  if (activeTab === "journey") {
    if (args.scopeMismatch) mainContentState = "scope_mismatch";
    else if (args.journeyQueryStatus === "loading") mainContentState = "loading";
    else if (args.journeyQueryStatus === "error") mainContentState = "request_error";
    else if (
      args.journeyStatus === "queued" ||
      args.journeyStatus === "running" ||
      args.journeyStatus === "scene_profiles_running" ||
      args.journeyStatus === "chapter_synthesis_running" ||
      (args.inFlight && !args.journeyAvailable)
    ) {
      mainContentState = "pending_generation";
    } else if (
      args.journeyIntegrityStatus === "data_integrity_failed" ||
      args.journeyIntegrityStatus === "invalid_context"
    ) {
      // Only hard-fail statuses block the whole Journey pane.
      mainContentState = "invalid_artifact";
    } else if (
      args.journeyAvailable ||
      args.journeyIntegrityStatus === "legacy_unverified" ||
      args.journeyIntegrityStatus === "partially_trusted" ||
      args.journeyIntegrityStatus === "trusted"
    ) {
      mainContentState = "ready";
    } else if (args.journeyQueryStatus === "success") mainContentState = "unavailable";
    else mainContentState = "loading";
  } else if (activeTab === "scene") {
    mainContentState = args.sceneAvailable || args.chapterComplete || args.inFlight ? "ready" : "loading";
  } else {
    mainContentState = "ready";
  }

  // User-pinned / explicit reading must stay shellView=reading even while analysis is in flight.
  // Only default in-flight text mode (progress URL or no reading pin) uses shellView=progress.
  const shellView: WorkspaceLayout["shellView"] =
    activeTab === "text"
      ? args.requestedView === "reading" || args.userPinnedTab === "text"
        ? "reading"
        : args.inFlight || args.requestedView === "progress"
          ? "progress"
          : "reading"
      : "result";

  const workspaceMode: WorkspaceLayout["workspaceMode"] =
    activeTab === "journey"
      ? "journey_result"
      : activeTab === "scene"
        ? "scene_result"
        : showProgressContext
          ? "progress"
          : "reading";

  const navigationPaneMode: WorkspaceLayout["navigationPaneMode"] =
    activeTab === "text" ? "chapter_nav" : "hidden";
  const contextPaneMode: WorkspaceLayout["contextPaneMode"] = showProgressContext
    ? "progress"
    : activeTab === "journey"
      ? "journey_detail"
      : activeTab === "scene"
        ? "scene_detail"
        : "hidden";

  return {
    activeTab,
    shellView,
    showNavigationInMain: activeTab === "text",
    showProgressContext,
    mainContentState,
    workspaceMode,
    navigationPaneMode,
    contextPaneMode,
  };
}
