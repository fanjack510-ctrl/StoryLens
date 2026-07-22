import { isRouteErrorResponse, useNavigate, useParams, useRouteError, useSearchParams } from "react-router-dom";
import { StateView } from "../components/ui/StateView";

function isDevMode(): boolean {
  return Boolean(import.meta.env.DEV);
}

function userFacingMessage(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    if (error.status === 404) return "页面不存在";
    return error.statusText || "页面加载失败";
  }
  if (error instanceof Error && error.message.trim()) {
    return "页面渲染时发生错误，请重新加载或返回书库。";
  }
  return "发生未知错误，请重新加载或返回书库。";
}

function sanitizeErrorMessage(message: string): string {
  return message
    .replace(/sk-[A-Za-z0-9._-]{8,}/g, "[redacted]")
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [redacted]")
    .replace(/[A-Za-z]:\\[^\s]+/g, "[path]")
    .replace(/\/(?:Users|home|var|tmp)\/[^\s]+/g, "[path]")
    .replace(/[A-Za-z0-9_.-]+\.(?:tsx?|jsx?|mjs|cjs):\d+/g, "[file]")
    .slice(0, 400);
}

function makeErrorId(error: unknown): string {
  const name = error instanceof Error ? error.name : "Unknown";
  const msg = error instanceof Error ? error.message : String(error);
  let hash = 0;
  const raw = `${name}:${msg}`;
  for (let i = 0; i < raw.length; i += 1) hash = (hash * 31 + raw.charCodeAt(i)) >>> 0;
  return `fe-${hash.toString(16).padStart(8, "0")}`;
}

/** Route-level runtime error page. Production never shows stacks or local paths. */
export function RouteErrorPage() {
  const error = useRouteError();
  const navigate = useNavigate();
  const params = useParams();
  const [searchParams] = useSearchParams();
  const message = userFacingMessage(error);
  const errorId = makeErrorId(error);
  const bookId = params.bookId || searchParams.get("book") || "—";
  const chapterId = searchParams.get("chapter") || "—";
  const analysisRunId = searchParams.get("analysisRun") || "—";
  const route =
    typeof window !== "undefined"
      ? `${window.location.pathname}${window.location.search}`
      : "—";
  const errorName = error instanceof Error ? error.name : isRouteErrorResponse(error) ? "RouteError" : "Unknown";
  const sanitized =
    error instanceof Error
      ? sanitizeErrorMessage(error.message)
      : isRouteErrorResponse(error)
        ? `${error.status} ${error.statusText || ""}`.trim()
        : "unknown";

  console.error("[route-error]", {
    error_id: errorId,
    route,
    book_id: bookId,
    chapter_id: chapterId,
    analysis_run_id: analysisRunId,
    error_name: errorName,
    message: sanitized,
    error,
  });

  if (isDevMode() && error instanceof Error) {
    console.error("[route-error-stack]", error);
  }

  return (
    <section className="page route-error-page" data-testid="route-error-page">
      <StateView
        kind="error"
        title="页面出错了"
        description={message}
        data-testid="route-error-state"
        primaryAction={{
          label: "重新加载",
          onClick: () => window.location.reload(),
          testId: "route-error-reload",
        }}
        secondaryAction={{
          label: "返回书库",
          onClick: () => navigate("/library"),
          variant: "secondary",
          testId: "route-error-library",
        }}
      />
      <details className="route-error-tech" data-testid="route-error-tech-details">
        <summary>查看技术详情</summary>
        <pre data-testid="route-error-tech-body">
          {`error_id=${errorId}
route=${route}
book_id=${bookId}
chapter_id=${chapterId}
analysis_run_id=${analysisRunId}
error_name=${errorName}
message=${sanitized}`}
        </pre>
      </details>
    </section>
  );
}

/** Chinese product 404 page. */
export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <section className="page not-found-page" data-testid="not-found-page">
      <StateView
        kind="empty"
        title="页面未找到"
        description="您访问的地址不存在，或内容已被移动。"
        data-testid="not-found-state"
        primaryAction={{
          label: "重新加载",
          onClick: () => window.location.reload(),
          testId: "not-found-reload",
        }}
        secondaryAction={{
          label: "返回书库",
          onClick: () => navigate("/library"),
          variant: "secondary",
          testId: "not-found-library",
        }}
      />
    </section>
  );
}
