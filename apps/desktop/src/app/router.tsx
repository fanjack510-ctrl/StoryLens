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

const routeErrorElement = <RouteErrorPage />;

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
      { path: "/tasks", element: <TasksPage />, errorElement: routeErrorElement },
      {
        path: "/analysis-runs/:runId/results",
        element: <AnalysisResultsShellPage />,
        errorElement: routeErrorElement,
      },
      { path: "/cases", element: <CasesPage />, errorElement: routeErrorElement },
      { path: "/providers", element: <ProvidersPage />, errorElement: routeErrorElement },
      { path: "/settings", element: <SettingsPage />, errorElement: routeErrorElement },
      { path: "*", element: <NotFoundPage />, errorElement: routeErrorElement },
    ],
  },
]);
