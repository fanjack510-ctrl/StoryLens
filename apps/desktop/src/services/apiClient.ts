let apiBase =
  typeof import.meta.env.VITE_API_BASE_URL === "string" && import.meta.env.VITE_API_BASE_URL.length > 0
    ? import.meta.env.VITE_API_BASE_URL
    : typeof import.meta.env.VITE_API_BASE_URL === "string" && import.meta.env.VITE_API_BASE_URL === ""
      ? ""
      : import.meta.env.DEV
        ? "http://127.0.0.1:8000"
        : "";

export function getApiBase(): string {
  return apiBase;
}

export function setApiBase(url: string): void {
  apiBase = url.replace(/\/$/, "");
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public detail?: unknown,
    public requestId?: string,
    public retryable?: boolean,
    public userActionHint?: string,
    public stage?: string,
    public required?: { requests?: number; tokens?: number; estimated_cost?: number },
    public remaining?: { requests?: number; tokens?: number; estimated_cost?: number },
    public exceededDimensions?: string[],
    public blockers?: string[],
    public providerName?: string,
  ) {
    super(message);
  }
}
function unwrapErrorPayload(payload: any): Record<string, any> {
  if (!payload || typeof payload !== "object") {
    return { message: String(payload || "请求失败") };
  }
  // FastAPI HTTPException: { detail: { error_code, message, ... } }
  if (payload.detail && typeof payload.detail === "object" && !Array.isArray(payload.detail)) {
    return { ...payload, ...payload.detail };
  }
  // FastAPI validation: { detail: [{ loc, msg, type }] }
  if (Array.isArray(payload.detail)) {
    const first = payload.detail[0];
    return {
      error_code: "REQUEST_VALIDATION_ERROR",
      message: first?.msg || "请求参数不合法",
      details: payload.detail,
      retryable: false,
    };
  }
  return payload;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}${path}`, {
      ...options,
      headers: {
        ...(options?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...options?.headers,
      },
    });
  } catch {
    throw new ApiError(
      "BACKEND_OFFLINE",
      "无法连接本地分析服务",
      0,
      {},
      undefined,
      true,
      "请确认 StoryLens 已完全启动；若刚打开，请稍等片刻后重试。若仍失败，请重启应用。",
    );
  }
  if (!response.ok) {
    let payload: any = {};
    try {
      payload = unwrapErrorPayload(await response.json());
    } catch {
      payload = { message: response.statusText || `HTTP ${response.status}` };
    }
    throw new ApiError(
      payload.error_code || "HTTP_ERROR",
      payload.message || payload.user_action_hint || `HTTP ${response.status}`,
      response.status,
      payload.details || payload.detail || payload,
      payload.request_id || response.headers.get("x-request-id") || undefined,
      payload.retryable,
      payload.user_action_hint,
      payload.stage,
      payload.required,
      payload.remaining,
      payload.exceeded_dimensions,
      payload.blockers || payload.details?.blockers,
      payload.provider_name || payload.details?.provider_name,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
