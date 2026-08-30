import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  ApiError,
  Job,
  JobResult,
  User,
  createJob,
  getJobResult,
  listJobs,
  login,
  logout,
  me,
  register,
  uploadTxt,
} from "./api";

const STATUS_LABELS: Record<Job["status"], string> = {
  queued: "等待处理",
  running: "处理中",
  succeeded: "已完成",
  failed: "处理失败",
};

const FAILURE_LABELS: Record<string, string> = {
  upload_missing: "上传文件不可用，请重新上传。",
  upload_integrity_mismatch: "文件完整性检查失败，请重新上传。",
  upload_invalid_encoding: "文件编码无效，请使用 UTF-8。",
  queue_unavailable: "任务队列暂时不可用。",
  processing_failed: "本地统计处理失败，请重新创建任务。",
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "操作失败，请稍后重试。";
}

export function App() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState("");

  const refreshJobs = useCallback(async () => {
    if (!user) return;
    try {
      setJobs(await listJobs());
    } catch (requestError) {
      setError(errorMessage(requestError));
    }
  }, [user]);

  useEffect(() => {
    void me()
      .then(setUser)
      .catch((requestError: unknown) => {
        if (!(requestError instanceof ApiError) || requestError.status !== 401) {
          setError(errorMessage(requestError));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (user) void refreshJobs();
  }, [refreshJobs, user]);

  useEffect(() => {
    if (!user || !jobs.some((job) => job.status === "queued" || job.status === "running")) {
      return;
    }
    const timer = window.setInterval(() => void refreshJobs(), 2000);
    return () => window.clearInterval(timer);
  }, [jobs, refreshJobs, user]);

  if (loading) {
    return <main className="centered">正在检查登录状态…</main>;
  }

  return (
    <main className="app-shell">
      <header className="site-header">
        <div>
          <span className="brand-mark">SL</span>
          <strong>StoryLens Online</strong>
          <span className="beta-badge">Hong Kong Beta</span>
        </div>
        {user && (
          <div className="account-actions">
            <span>{user.email}</span>
            <button
              className="quiet-button"
              onClick={() => void logout().then(() => setUser(null))}
              type="button"
            >
              退出登录
            </button>
          </div>
        )}
      </header>

      <section className="notice" aria-label="阶段说明">
        <strong>Phase 2A 链路验证</strong>
        <span>只执行本地文本统计，不调用 AI，不产生费用。</span>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button type="button" onClick={() => setError("")} aria-label="关闭错误提示">
            ×
          </button>
        </div>
      )}

      {user ? (
        <Dashboard
          jobs={jobs}
          result={result}
          onJobsChanged={refreshJobs}
          onResult={setResult}
          onError={(requestError) => setError(errorMessage(requestError))}
        />
      ) : (
        <AuthPanel onAuthenticated={setUser} onError={(message) => setError(message)} />
      )}
    </main>
  );
}

function AuthPanel({
  onAuthenticated,
  onError,
}: {
  onAuthenticated: (user: User) => void;
  onError: (message: string) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const user = mode === "login"
        ? await login(email, password)
        : await register(email, password);
      onAuthenticated(user);
    } catch (requestError) {
      onError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="auth-panel">
      <p className="eyebrow">开始链路验证</p>
      <h1>{mode === "login" ? "登录 StoryLens Online" : "创建 Beta 账户"}</h1>
      <p>账户只用于隔离你的上传和任务，不会接触 PocketBase 管理权限。</p>
      <div className="mode-switch" role="tablist" aria-label="认证方式">
        <button type="button" onClick={() => setMode("login")} aria-selected={mode === "login"}>
          登录
        </button>
        <button
          type="button"
          onClick={() => setMode("register")}
          aria-selected={mode === "register"}
        >
          注册
        </button>
      </div>
      <form onSubmit={(event) => void submit(event)}>
        <label>
          邮箱
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          密码（至少 10 位）
          <input
            type="password"
            minLength={10}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
          />
        </label>
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "提交中…" : mode === "login" ? "登录" : "注册并登录"}
        </button>
      </form>
    </section>
  );
}

function Dashboard({
  jobs,
  result,
  onJobsChanged,
  onResult,
  onError,
}: {
  jobs: Job[];
  result: JobResult | null;
  onJobsChanged: () => Promise<void>;
  onResult: (result: JobResult | null) => void;
  onError: (error: unknown) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setSubmitting(true);
    onResult(null);
    try {
      const saved = await uploadTxt(file);
      await createJob(saved.id, crypto.randomUUID());
      setFile(null);
      await onJobsChanged();
    } catch (requestError) {
      onError(requestError);
    } finally {
      setSubmitting(false);
    }
  }

  async function showResult(jobId: string) {
    try {
      onResult(await getJobResult(jobId));
    } catch (requestError) {
      onError(requestError);
    }
  }

  return (
    <div className="dashboard-grid">
      <section className="panel upload-panel">
        <p className="eyebrow">01 上传</p>
        <h1>上传 UTF-8 TXT</h1>
        <p>单个文件最大 10MB。文件名仅用于展示，服务端会生成独立存储键。</p>
        <form onSubmit={(event) => void submit(event)}>
          <label className="file-picker">
            <span>{file?.name ?? "选择 TXT 文件"}</span>
            <input
              aria-label="选择 TXT 文件"
              type="file"
              accept=".txt,text/plain"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button className="primary-button" type="submit" disabled={!file || submitting}>
            {submitting ? "创建任务中…" : "上传并创建统计任务"}
          </button>
        </form>
      </section>

      <section className="panel jobs-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">02 任务</p>
            <h2>我的任务</h2>
          </div>
          <button className="quiet-button" type="button" onClick={() => void onJobsChanged()}>
            刷新
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="empty-state">还没有任务。上传 TXT 后会显示处理进度。</p>
        ) : (
          <ul className="job-list">
            {jobs.map((job) => (
              <li key={job.id}>
                <div className="job-row">
                  <div>
                    <strong>{STATUS_LABELS[job.status]}</strong>
                    <code>{job.id.slice(0, 8)}</code>
                  </div>
                  <span>{job.progress}%</span>
                </div>
                <progress max="100" value={job.progress} />
                {job.status === "failed" && (
                  <p className="job-error">
                    {FAILURE_LABELS[job.public_error_code ?? ""] ?? "任务处理失败。"}
                  </p>
                )}
                {job.status === "succeeded" && (
                  <button className="text-button" type="button" onClick={() => void showResult(job.id)}>
                    查看统计结果
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel result-panel">
        <p className="eyebrow">03 结果</p>
        <h2>本地文本统计</h2>
        {!result ? (
          <p className="empty-state">任务完成后选择“查看统计结果”。</p>
        ) : (
          <div className="result-grid">
            <ResultMetric label="字符数" value={result.result.character_count.toLocaleString()} />
            <ResultMetric label="非空行" value={result.result.nonempty_line_count.toLocaleString()} />
            <ResultMetric label="文件字节" value={result.result.file_size_bytes.toLocaleString()} />
            <ResultMetric label="处理耗时" value={`${result.result.processing_duration_ms} ms`} />
            <div className="hash-row">
              <span>SHA256</span>
              <code>{result.result.sha256}</code>
            </div>
            <div className="result-boundary">
              <span>AI 分析：未执行</span>
              <span>计费：¥0</span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
