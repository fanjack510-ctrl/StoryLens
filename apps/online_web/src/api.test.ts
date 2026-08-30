import { afterEach, describe, expect, it, vi } from "vitest";

import { createJob, uploadTxt } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("online API client", () => {
  it("uploads TXT with cookies and multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "upload-1",
          original_filename: "book.txt",
          sha256: "a".repeat(64),
          file_size_bytes: 5,
          created_at: "2026-08-30T00:00:00Z",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadTxt(new File(["hello"], "book.txt", { type: "text/plain" }));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/uploads");
    expect(options.credentials).toBe("include");
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.headers).toBeUndefined();
  });

  it("creates a job with the supplied idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "job-1",
          upload_id: "upload-1",
          pipeline: "phase2a_smoke",
          status: "queued",
          progress: 0,
          public_error_code: null,
          created_at: "2026-08-30T00:00:00Z",
          started_at: null,
          finished_at: null,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createJob("upload-1", "browser-request-1");
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(options.credentials).toBe("include");
    expect(JSON.parse(String(options.body))).toEqual({
      upload_id: "upload-1",
      idempotency_key: "browser-request-1",
      pipeline: "phase2a_smoke",
    });
  });

  it("sends the allowlisted evidence pipeline without Provider configuration", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "job-2",
          upload_id: "upload-1",
          pipeline: "phase2b1_txt_evidence_summary",
          status: "queued",
          progress: 0,
          public_error_code: null,
          created_at: "2026-08-30T00:00:00Z",
          started_at: null,
          finished_at: null,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createJob("upload-1", "browser-request-2", "phase2b1_txt_evidence_summary");
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(options.body))).toEqual({
      upload_id: "upload-1",
      idempotency_key: "browser-request-2",
      pipeline: "phase2b1_txt_evidence_summary",
    });
    expect(String(options.body)).not.toContain("provider");
    expect(String(options.body)).not.toContain("model");
  });
});
