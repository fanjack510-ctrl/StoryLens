import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { HomePage } from "../pages/HomePage";
import { LibraryPage } from "../pages/LibraryPage";
import { CommonPatternsPage } from "../pages/CommonPatternsPage";
import { CrossBookSearchPage } from "../pages/CrossBookSearchPage";
import { CapabilitiesPage } from "../pages/CapabilitiesPage";
import { CommonPatternsStartPage } from "../pages/CommonPatternsStartPage";
import { BookRoutePage } from "../pages/BookRoutePage";
import { WorkspaceLandingPage } from "../pages/WorkspaceLandingPage";
import { TasksPage } from "../pages/TasksPage";
import { AnalysisResultsShellPage } from "../pages/AnalysisResultsShellPage";
import { CasesPage } from "../pages/CasesPage";
import { SettingsPage } from "../pages/SettingsPage";
import { WholeBookInsightsPage } from "../pages/WholeBookInsightsPage";
import { ProNativeOverviewPage } from "../pages/ProNativeOverviewPage";
import { WholeBookDiagnosticsPage } from "../pages/WholeBookDiagnosticsPage";
import { ChapterFunctionsHarnessPage } from "../pages/ChapterFunctionsHarnessPage";
import { NotFoundPage, RouteErrorPage } from "../pages/RouteErrorPages";
import { WholeBookV2FormalPage } from "../features/wholeBookV2/WholeBookV2FormalPage";
import { WholeBookV2ProductPage } from "../features/wholeBookV2/WholeBookV2ProductPage";
import { ShortFormPage } from "../features/shortForm/ShortFormPage";

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
      {
        // 「能做什么」——这个产品 17 个页面，顶栏只挂 3 个，其余全靠撞见。
        // 这一页是那份缺失的地图，免费的和付费的排在一起。
        path: "/capabilities",
        element: <CapabilitiesPage />,
        errorElement: routeErrorElement,
      },
      {
        // 旧的 /pro 是「专业版能做什么」，只列收费项。它答不了用户真正问的
        // 「到底能干哪些功能」，所以并进 /capabilities。**保留重定向**：
        // 界面里到处都是 /pro#pro-item-xxx 的锚点链接，而锚点在新页面里还在。
        path: "/pro",
        element: <Navigate to="/capabilities" replace />,
        errorElement: routeErrorElement,
      },
      {
        path: "/search",
        element: <CrossBookSearchPage />,
        errorElement: routeErrorElement,
      },
      {
        path: "/knowledge",
        lazy: async () => ({
          Component: (await import("../pages/KnowledgeLibraryPage")).KnowledgeLibraryPage,
        }),
        errorElement: routeErrorElement,
      },
      {
        // 共性视图的入口：先挑书，再比较。
        // 圈书原来在书库筛选条上，用户问「为啥上来要建书单」——他是对的，
        // 书单是比较的副产物，不是前置条件。
        path: "/patterns",
        element: <CommonPatternsStartPage />,
        errorElement: routeErrorElement,
      },
      {
        // 共性视图挂在书单下面而不是书下面：它比的是一组书，不是一本。
        path: "/collections/:collectionId/patterns",
        element: <CommonPatternsPage />,
        errorElement: routeErrorElement,
      },
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
        element: <WholeBookV2ProductPage />,
        errorElement: routeErrorElement,
      },
      {
        // Its own route rather than a mode of the whole-book page: a short piece is read in
        // one sitting and measured in scenes, and nothing on that page applies to it.
        path: "/books/:bookId/short-form",
        element: <ShortFormPage />,
        errorElement: routeErrorElement,
      },
      {
        // Ahead of the analysis, not inside it: the profile is a book-level prerequisite
        // that both the whole-book engine and the per-chapter pipeline read.
        path: "/books/:bookId/profile",
        lazy: async () => ({
          Component: (await import("../features/bookProfile/BookProfilePage")).BookProfilePage,
        }),
        errorElement: routeErrorElement,
      },
      {
        // 旧收藏地址只做兼容。知识库是全局页面，不属于任何一本书。
        path: "/books/:bookId/material-lab",
        element: <Navigate to="/knowledge" replace />,
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
      { path: "/settings", element: <SettingsPage />, errorElement: routeErrorElement },
      ...devOnlyChildren,
      { path: "*", element: <NotFoundPage />, errorElement: routeErrorElement },
    ],
  },
]);
