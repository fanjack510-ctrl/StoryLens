import { describe, expect, it } from "vitest";
import { ApiError } from "./apiClient";
import { mapTaskCenterError } from "./taskCenterErrors";

describe("mapTaskCenterError", () => {
  it("keeps 422 business errors out of offline copy", () => {
    const view = mapTaskCenterError(
      new ApiError("CLOUD_MODE_REQUIRED", "云端 Provider 需要 cloud 或 hybrid 模式", 422),
    );
    expect(view.code).toBe("CLOUD_MODE_REQUIRED");
    expect(view.message).toContain("CLOUD_MODE_REQUIRED");
    expect(view.message).not.toContain("无法连接本地分析服务");
  });

  it("maps offline fetch failures", () => {
    const view = mapTaskCenterError(
      new ApiError("BACKEND_OFFLINE", "无法连接本地分析服务", 0),
    );
    expect(view.code).toBe("LOCAL_SERVICE_UNAVAILABLE");
    expect(view.message).toContain("无法连接本地分析服务");
  });

  it("maps HTTP 500", () => {
    const view = mapTaskCenterError(new ApiError("HTTP_ERROR", "boom", 500));
    expect(view.code).toBe("HTTP_ERROR");
    expect(view.httpStatus).toBe(500);
  });
});
