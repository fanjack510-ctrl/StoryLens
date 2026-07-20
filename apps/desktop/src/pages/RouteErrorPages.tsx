import { isRouteErrorResponse, Link, useNavigate, useRouteError } from "react-router-dom";

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
      <div className="state error" role="alert">
        <p className="eyebrow">StoryLens</p>
        <h1>页面出错了</h1>
        <p>{message}</p>
        <div className="route-error-actions">
          <button
            type="button"
            className="primary"
            data-testid="route-error-reload"
            onClick={() => window.location.reload()}
          >
            重新加载
          </button>
          <button
            type="button"
            data-testid="route-error-library"
            onClick={() => navigate("/library")}
          >
            返回书库
          </button>
          <Link to="/library">前往书库</Link>
        </div>
      </div>
    </section>
  );
}

/** Chinese product 404 page. */
export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <section className="page not-found-page" data-testid="not-found-page">
      <div className="state">
        <p className="eyebrow">StoryLens</p>
        <h1>页面未找到</h1>
        <p>您访问的地址不存在，或内容已被移动。</p>
        <div className="route-error-actions">
          <button
            type="button"
            className="primary"
            data-testid="not-found-reload"
            onClick={() => window.location.reload()}
          >
            重新加载
          </button>
          <button
            type="button"
            data-testid="not-found-library"
            onClick={() => navigate("/library")}
          >
            返回书库
          </button>
          <Link to="/library">前往书库</Link>
        </div>
      </div>
    </section>
  );
}
