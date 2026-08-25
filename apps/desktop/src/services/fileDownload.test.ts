import { afterEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import { saveBlobAsFile, savedFileMessage } from "./fileDownload";

afterEach(() => {
  vi.restoreAllMocks();
  invoke.mockReset();
  delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
});

describe("saveBlobAsFile", () => {
  it("delegates installed desktop saves to the native Downloads command", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      value: {},
      configurable: true,
    });
    invoke.mockResolvedValue("C:\\Users\\reader\\Downloads\\报告.pdf");

    const result = await saveBlobAsFile(
      new Blob([new Uint8Array([37, 80, 68, 70])], { type: "application/pdf" }),
      "报告.pdf",
    );

    expect(invoke).toHaveBeenCalledWith("save_download_file", {
      filename: "报告.pdf",
      bytes: [37, 80, 68, 70],
    });
    expect(savedFileMessage(result)).toBe(
      "已保存到：C:\\Users\\reader\\Downloads\\报告.pdf",
    );
  });

  it("keeps browser development downloads working", async () => {
    const createObjectURL = vi.fn(() => "blob:storylens");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const result = await saveBlobAsFile(new Blob(["pdf"]), "报告.pdf");

    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:storylens");
    expect(savedFileMessage(result)).toBe("已开始下载：报告.pdf");
  });
});
