import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router-dom";
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

/** Route-level runtime error page. Production never shows stacks or local paths. */
export function RouteErrorPage() {
  const error = useRouteError();
  const navigate = useNavigate();
  const message = userFacingMessage(error);

  if (isDevMode() && error instanceof Error) {
    console.error("[route-error]", error);
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
