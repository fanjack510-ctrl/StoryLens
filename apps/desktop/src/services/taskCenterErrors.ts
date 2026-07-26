import { ApiError } from "./apiClient";

export type TaskCenterErrorView = {
  code: string;
  title: string;
  message: string;
  httpStatus: number;
  requestId?: string;
  retryable?: boolean;
};

/** Map task-list failures without collapsing business errors into "offline". */
export function mapTaskCenterError(error: unknown): TaskCenterErrorView {
  if (error instanceof ApiError) {
    if (error.code === "BACKEND_OFFLINE" || error.status === 0) {
      return {
        code: "LOCAL_SERVICE_UNAVAILABLE",
        title: "无法读取数据",
        message: "无法连接本地分析服务",
        httpStatus: 0,
        requestId: error.requestId,
        retryable: true,
      };
    }
    if (error.status === 401) {
      return {
        code: "HTTP_401",
        title: "无法读取数据",
        message: error.message || "未授权访问任务列表",
        httpStatus: 401,
        requestId: error.requestId,
        retryable: false,
      };
    }
    if (error.status === 403) {
      return {
        code: "HTTP_403",
        title: "无法读取数据",
        message: error.message || "没有权限读取任务列表",
        httpStatus: 403,
        requestId: error.requestId,
        retryable: false,
      };
    }
    if (error.status === 404) {
      return {
        code: "HTTP_404",
        title: "无法读取数据",
        message: error.message || "任务列表接口不存在",
        httpStatus: 404,
        requestId: error.requestId,
        retryable: false,
      };
    }
    if (error.status === 422) {
      return {
        code: error.code || "HTTP_422",
        title: "无法读取数据",
        message: `任务列表请求失败：${error.code || "HTTP_422"}${
          error.message ? `（${error.message}）` : ""
        }`,
        httpStatus: 422,
        requestId: error.requestId,
        retryable: Boolean(error.retryable),
      };
    }
    if (error.status >= 500) {
      return {
        code: error.code || "HTTP_500",
        title: "无法读取数据",
        message: error.message || "任务列表服务内部错误",
        httpStatus: error.status,
        requestId: error.requestId,
        retryable: true,
      };
    }
    return {
      code: error.code || "TASK_LIST_LOAD_FAILED",
      title: "无法读取数据",
      message: error.message || "任务列表加载失败",
      httpStatus: error.status,
      requestId: error.requestId,
      retryable: error.retryable,
    };
  }

  if (error instanceof TypeError) {
    return {
      code: "NETWORK_UNREACHABLE",
      title: "无法读取数据",
      message: "网络不可达，无法连接本地分析服务",
      httpStatus: 0,
      retryable: true,
    };
  }

  const message = error instanceof Error ? error.message : "任务列表加载失败";
  return {
    code: "TASK_LIST_LOAD_FAILED",
    title: "无法读取数据",
    message,
    httpStatus: 0,
    retryable: true,
  };
}
