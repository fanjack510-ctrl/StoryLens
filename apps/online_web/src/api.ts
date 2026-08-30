export interface User {
  id: string;
  email: string;
}

export interface UploadRecord {
  id: string;
  original_filename: string;
  sha256: string;
  file_size_bytes: number;
  created_at: string;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job {
  id: string;
  upload_id: string;
  pipeline: "phase2a_smoke";
  status: JobStatus;
  progress: number;
  public_error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Phase2AResult {
  pipeline: "phase2a_smoke";
  character_count: number;
  nonempty_line_count: number;
  file_size_bytes: number;
  sha256: string;
  processing_duration_ms: number;
  real_ai_analysis: false;
  billing_status: "not_billable";
  charged_cny: 0;
}

export interface JobResult {
  job_id: string;
  result: Phase2AResult;
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string };
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: init.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    let body: ErrorEnvelope = {};
    try {
      body = (await response.json()) as ErrorEnvelope;
    } catch {
      // The public fallback below intentionally ignores non-JSON internal responses.
    }
    throw new ApiError(
      response.status,
      body.error?.code ?? "request_failed",
      body.error?.message ?? "请求失败，请稍后重试。",
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function register(email: string, password: string): Promise<User> {
  return request<User>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<User> {
  return request<User>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return request<void>("/api/v1/auth/logout", { method: "POST" });
}

export function me(): Promise<User> {
  return request<User>("/api/v1/auth/me");
}

export function uploadTxt(file: File): Promise<UploadRecord> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadRecord>("/api/v1/uploads", { method: "POST", body: form });
}

export function createJob(uploadId: string, idempotencyKey: string): Promise<Job> {
  return request<Job>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify({ upload_id: uploadId, idempotency_key: idempotencyKey }),
  });
}

export function listJobs(): Promise<Job[]> {
  return request<Job[]>("/api/v1/jobs");
}

export function getJobResult(jobId: string): Promise<JobResult> {
  return request<JobResult>(`/api/v1/jobs/${jobId}/result`);
}
