import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { HomePage } from "../pages/HomePage";
import { LibraryPage } from "../pages/LibraryPage";
import { BookRoutePage } from "../pages/BookRoutePage";
import { WorkspaceLandingPage } from "../pages/WorkspaceLandingPage";
import { TasksPage } from "../pages/TasksPage";
import { AnalysisResultsShellPage } from "../pages/AnalysisResultsShellPage";
import { CasesPage } from "../pages/CasesPage";
import { ProvidersPage } from "../pages/ProvidersPage";
import { SettingsPage } from "../pages/SettingsPage";
import { WholeBookInsightsPage } from "../pages/WholeBookInsightsPage";
import { ProNativeOverviewPage } from "../pages/ProNativeOverviewPage";
import { WholeBookDiagnosticsPage } from "../pages/WholeBookDiagnosticsPage";
import { WholeBookFreeProductPage } from "../pages/WholeBookFreeProductPage";
import { ChapterFunctionsHarnessPage } from "../pages/ChapterFunctionsHarnessPage";
import { NotFoundPage, RouteErrorPage } from "../pages/RouteErrorPages";
import { WholeBookV2FormalPage } from "../features/wholeBookV2/WholeBookV2FormalPage";

const routeErrorElement = <RouteErrorPage />;

/** Dev/test-only routes — excluded from production builds (import.meta.env.DEV). */
const devOnlyChildren = import.meta.env.DEV
  ? [
      {
        path: "/dev/whole-book-v2-mock",
        lazy: async () => ({
          Component: (await import("../features/wholeBookV2Mock/WholeBookV2MockPage"))
            .WholeBookV2MockPage,
        }),
        errorElement: routeErrorElement,
      },
      {
        path: "/dev/whole-book-v2-mock/progress",
        lazy: async () => ({
          Component: (await import("../features/wholeBookV2Mock/WholeBookV2ProgressMockPage"))
            .WholeBookV2ProgressMockPage,
        }),
        errorElement: routeErrorElement,
      },
      {
        path: "/dev/whole-book-diagnostics",
        element: <WholeBookDiagnosticsPage />,
        errorElement: routeErrorElement,
      },
      {
        // TEST-ONLY harness — not in Free product nav; Playwright uses Vite DEV server.
        path: "/dev/whole-book-free-chapter-functions-harness",
        element: <ChapterFunctionsHarnessPage />,
        errorElement: routeErrorElement,
      },
    ]
  : [];

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    errorElement: routeErrorElement,
    children: [
      { path: "/", element: <HomePage />, errorElement: routeErrorElement },
      { path: "/library", element: <LibraryPage />, errorElement: routeErrorElement },
      { path: "/workspace", element: <WorkspaceLandingPage />, errorElement: routeErrorElement },
      { path: "/books/:bookId", element: <BookRoutePage />, errorElement: routeErrorElement },
      {
        path: "/books/:bookId/whole-book-insights",
        element: <WholeBookInsightsPage />,
        errorElement: routeErrorElement,
      },
      {
        path: "/books/:bookId/pro-native-overview",
        element: <ProNativeOverviewPage />,
        errorElement: routeErrorElement,
      },
      {
        path: "/books/:bookId/whole-book",
        element: <WholeBookFreeProductPage />,
        errorElement: routeErrorElement,
      },
      {
        path: "/books/:bookId/whole-book-v2",
        element: <WholeBookV2FormalPage />,
        errorElement: routeErrorElement,
      },
      { path: "/tasks", element: <TasksPage />, errorElement: routeErrorElement },
      {
        path: "/analysis-runs/:runId/results",
        element: <AnalysisResultsShellPage />,
        errorElement: routeErrorElement,
      },
      { path: "/cases", element: <CasesPage />, errorElement: routeErrorElement },
      { path: "/providers", element: <ProvidersPage />, errorElement: routeErrorElement },
      { path: "/settings", element: <SettingsPage />, errorElement: routeErrorElement },
      ...devOnlyChildren,
      { path: "*", element: <NotFoundPage />, errorElement: routeErrorElement },
    ],
  },
]);
