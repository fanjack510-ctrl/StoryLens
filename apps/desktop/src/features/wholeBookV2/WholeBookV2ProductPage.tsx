import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState, Loading } from "../../components/common/States";
import { ComprehendReportView } from "./presentation/ComprehendReportView";
import { getComprehendResult } from "./api";
import { ApiError } from "../../services/apiClient";
import { profileHref } from "../bookProfile/origin";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";
import { isWholeBookRealProviderEnabled } from "../../services/wholeBookRealProviderFlag";
import { settingsApi } from "../../services/settingsApi";
import { AnalysisFormSwitch } from "../../components/shortForm/AnalysisFormSwitch";
import {
  compareLimitsToEstimate,
  formatLimitGapsMessage,
  mapWholeBookStartError,
} from "../../services/wholeBookStartLimits";
import {
  newWholeBookClientRequestId,
  wholeBookFreeProductApi,
  type WholeBookAnalysisMode,
  type WholeBookPrepareResponse,
  type WholeBookRunRecord,
} from "../../services/wholeBookFreeProductApi";
import { getWholeBookV2, getWholeBookV2Progress } from "./api";
import { V2_PROGRESS_LABELS } from "./contracts";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";
import type { ModuleKey } from "./presentation/modules";
import "./formal.css";

const PAGE_TITLE = "全书分析";
const PAGE_DESCRIPTION =
  "从完整原文出发，分析全书总览、故事、人物、悬念、节奏、章节与综合诊断。";
const PREPARE_EXPLANATION =
  "StoryLens 将读取整本小说原文，生成 Whole-Book V2 完整分析报告。分析结果可以回到原文核对。";
const PREPARE_BULLETS = [
  "分析使用您配置的大模型 API；模型费用由模型服务商收取。",
  "原始小说不会上传到 StoryLens 官方服务器。",
  "当前分析以完整原文为事实源，不依赖已有单章分析。",
];
const CONSENT_TEXT = "我已了解本次分析会调用我配置的大模型 API，并可能产生模型费用。";

/** The two readings, and what each is *for*. Wording matters more than usual here: a user who
 *  picks the wrong one pays for a report answering a question they did not ask. So each option
 *  names whose book it suits rather than describing its contents. */
const ANALYSIS_MODES: ReadonlyArray<{
  value: WholeBookAnalysisMode;
  label: string;
  hint: string;
}> = [
  {
    value: "diagnostic",
    label: "评测",
    hint: "看自己的书：找出该改哪里、为什么、动的时候不能损伤什么。",
  },
  {
    value: "story_breakdown",
    label: "拆文",
    hint: "看别人的书：起承转合、爆点在哪、钩子怎么下、哪些写法可以拿走用。不打分。",
  },
  {
    value: "comprehend",
    label: "读懂",
    hint: "看不是小说的书：专著、教材、工具书。逐节给出主张、依据、能照做的动作和术语对照，读英文原书也出中文。",
  },
];
const REANALYSE_CONSENT_TEXT =
  "我已了解重新分析会调用我配置的大模型 API，并可能产生模型费用。";

type PageMode =
  | "prepare"
  | "reanalyse-confirm"
  | "running"
  | "completed-v2"
  | "legacy"
  | "failed";

type RunningSubview = "progress" | "old-result";

function isActiveRun(status: string | null | undefined): boolean {
  return status === "running" || status === "paused" || status === "recoverable";
}

function isCompletedRun(status: string | null | undefined): boolean {
  return status === "completed";
}

function isFailedRun(status: string | null | undefined): boolean {
  return status === "failed" || status === "cancelled" || status === "canceled";
}

function isLegacyV2Error(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.status === 404) return true;
  if (err.code === "WHOLE_BOOK_V2_RESULT_NOT_FOUND") return true;
  if (err.message.includes("WHOLE_BOOK_V2")) return true;
  return false;
}

function resolveActiveRun(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  // 谁还在跑，由后端说了算（INV-P4）。
  //
  // 以前这里自己挑：active_run 空了看 latest_run，再空看 recoverable_run，只要状态是
  // running/paused/recoverable 就当成「正在进行」。于是一个进程早已消失、状态还停在 running
  // 的空壳会把开始按钮永久堵住——《余罪》就是这样，只能靠手工调接口才解得开。而客户端凭状态
  // 字段永远分不出「在跑」和「死了但没人改状态」。
  //
  // 后端用心跳判活并给出 live_run_id：为 null 就是没有在跑的任务，该显示开始按钮。
  if (prepare.live_run_id != null) {
    for (const run of [prepare.active_run, prepare.latest_run, prepare.recoverable_run]) {
      if (run && run.run_id === prepare.live_run_id) return run;
    }
  }
  // 后端还没有这个字段（旧版本）时，退回原来的挑法，而不是把页面变成空白。
  if (prepare.live_run_id === undefined) {
    if (prepare.active_run && isActiveRun(prepare.active_run.status)) return prepare.active_run;
    if (prepare.latest_run && isActiveRun(prepare.latest_run.status)) return prepare.latest_run;
    if (prepare.recoverable_run && isActiveRun(prepare.recoverable_run.status)) {
      return prepare.recoverable_run;
    }
  }
  return null;
}

function resolveCompletedV2Run(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  // CHG-084: only backend-gated real_provider completed rows — never fall back to scaffold.
  if (prepare.completed_v2_run && isCompletedRun(prepare.completed_v2_run.status)) {
    return prepare.completed_v2_run;
  }
  return null;
}

function resolveLatestFailedRun(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  if (prepare.latest_failed_run && isFailedRun(prepare.latest_failed_run.status)) {
    return prepare.latest_failed_run;
  }
  if (prepare.latest_run && isFailedRun(prepare.latest_run.status)) {
    return prepare.latest_run;
  }
  return null;
}

function resolveNonRealCompletedRun(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  if (
    prepare.non_real_completed_v2_run &&
    isCompletedRun(prepare.non_real_completed_v2_run.status)
  ) {
    return prepare.non_real_completed_v2_run;
  }
  return null;
}

function ProductUnavailable() {
  return (
    <section className="wbv2-state" data-testid="whole-book-v2-unavailable">
      <h1>{PAGE_TITLE}</h1>
      <p>正式全书分析入口未启用。</p>
      <p className="muted">
        <Link to="/library">返回书库</Link>
      </p>
    </section>
  );
}

type LimitsState = {
  max_provider_calls: string;
  max_input_tokens: string;
  max_output_tokens: string;
  max_cost_budget_cny: string;
};

function LimitsInputs({
  limits,
  onLimitsChange,
  limitGaps,
}: {
  limits: LimitsState;
  onLimitsChange: (next: LimitsState) => void;
  limitGaps: ReturnType<typeof compareLimitsToEstimate>;
}) {
  return (
    <>
      <div className="wbv2-limits">
        <label>
          最大调用次数
          <input
            value={limits.max_provider_calls}
            onChange={(e) => onLimitsChange({ ...limits, max_provider_calls: e.target.value })}
          />
        </label>
        <label>
          最大输入 tokens
          <input
            value={limits.max_input_tokens}
            onChange={(e) => onLimitsChange({ ...limits, max_input_tokens: e.target.value })}
          />
        </label>
        <label>
          最大输出 tokens
          <input
            value={limits.max_output_tokens}
            onChange={(e) => onLimitsChange({ ...limits, max_output_tokens: e.target.value })}
          />
        </label>
        <label>
          费用上限（元）
          <input
            value={limits.max_cost_budget_cny}
            onChange={(e) => onLimitsChange({ ...limits, max_cost_budget_cny: e.target.value })}
          />
        </label>
      </div>
      {limitGaps.length > 0 ? (
        <p className="wbv2-warning">{formatLimitGapsMessage(limitGaps)}</p>
      ) : null}
    </>
  );
}

function PreparePanel({
  prepare,
  consented,
  onConsent,
  canStart,
  starting,
  onStart,
  actionError,
  limits,
  onLimitsChange,
  limitGaps,
  profileConfirmed,
  bookId,
  analysisMode,
  onAnalysisModeChange,
}: {
  prepare: WholeBookPrepareResponse;
  consented: boolean;
  onConsent: (v: boolean) => void;
  canStart: boolean;
  starting: boolean;
  onStart: () => void;
  actionError: string | null;
  limits: LimitsState;
  onLimitsChange: (next: LimitsState) => void;
  limitGaps: ReturnType<typeof compareLimitsToEstimate>;
  /** null = still reading. The gate is only asserted once the answer is known. */
  profileConfirmed: boolean | null;
  bookId: number;
  analysisMode: WholeBookAnalysisMode;
  onAnalysisModeChange: (next: WholeBookAnalysisMode) => void;
}) {
  const est = prepare.estimate;
  // 「读懂」不过画像门。画像的五根轴是付费模式 / 读者 / 爽感引擎 / 人称 / 篇幅——全是网文的
  // 东西；它决定的是小说分析走哪个引擎、量哪几条类型轴，而读懂一条都不用。后端已经放行了，
  // 前端这里不跟上，按钮照样是灰的——那等于没放行。
  const profileGateClosed = profileConfirmed === false && analysisMode !== "comprehend";
  const breakdownAvailable = prepare.planner === "long_novel_engine";
  return (
    <section className="wbv2-prepare" data-testid="whole-book-v2-prepare">
      <h2>开始全书分析</h2>
      {/* Stated on open rather than after the click: a hard gate the user cannot see is
          experienced as a failure, not as a step. Same treatment the chapter dialog got. */}
      {profileGateClosed && (
        <div className="wbv2-profile-gate" data-testid="whole-book-v2-profile-gate" role="alert">
          <b>开始分析前，请先确认这本书的作品画像</b>
          <p>画像决定分析按什么类型侧重进行（升级流看爽点、悬疑看线索、情感看节拍）。一本书只需确认一次。</p>
          <Link to={profileHref(bookId, { from: "whole-book" })}>去确认作品画像 →</Link>
        </div>
      )}
      <AnalysisModeFieldset
        analysisMode={analysisMode}
        onAnalysisModeChange={onAnalysisModeChange}
        breakdownAvailable={breakdownAvailable}
      />
      <p>{PREPARE_EXPLANATION}</p>
      <ul>
        {PREPARE_BULLETS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {est ? (
        <p data-testid="whole-book-v2-estimate">
          预估调用 {est.estimated_provider_calls ?? "—"} 次 · 费用{" "}
          {est.estimated_cost_min_cny && est.estimated_cost_max_cny
            ? `约 ¥${est.estimated_cost_min_cny}～¥${est.estimated_cost_max_cny}`
            : "—"}
        </p>
      ) : null}
      <LimitsInputs limits={limits} onLimitsChange={onLimitsChange} limitGaps={limitGaps} />
      <label className="wbv2-consent">
        <input type="checkbox" checked={consented} onChange={(e) => onConsent(e.target.checked)} />
        {CONSENT_TEXT}
      </label>
      {actionError ? <p className="wbv2-error">{actionError}</p> : null}
      <button type="button" disabled={!canStart || profileGateClosed} onClick={onStart}>
        {starting ? "创建中…" : "开始全书分析"}
      </button>
      {profileGateClosed && <p className="wbv2-reanalyse-meta">需要先确认作品画像</p>}
    </section>
  );
}

/** 评测 / 拆文. Rendered by both the first-run panel and the re-analysis panel.
 *
 *  It used to live only in the first-run panel, so once a book had a result there was no way
 *  to ask for the other reading — and 重新分析 quietly re-ran whatever the component state
 *  happened to hold, which was 评测 by default. A book analysed as 拆文 could be re-run as a
 *  diagnostic without the person clicking ever being shown the choice.
 */
/** 评测 ⇄ 拆文, when the book has both.
 *
 *  They answer different questions and neither replaces the other, but the page showed only
 *  whichever run finished last. Running the second reading therefore made the first one
 *  unreachable — paid for, stored, and with no way back to it.
 *
 *  Nothing renders when a book has fewer than two readings: a switch with one position is
 *  not a switch.
 */
function ReadingSwitch({
  readings,
  current,
  onChange,
}: {
  readings: ReadonlyArray<{ value: WholeBookAnalysisMode; label: string }>;
  current: WholeBookAnalysisMode | null;
  onChange: (next: WholeBookAnalysisMode) => void;
}) {
  if (readings.length < 2) return null;
  return (
    <div className="wbv2-reading-switch" data-testid="whole-book-v2-reading-switch">
      <span>这本书有两份报告</span>
      {readings.map((r) => (
        <button
          key={r.value}
          type="button"
          className={r.value === current ? "active" : ""}
          aria-pressed={r.value === current}
          onClick={() => onChange(r.value)}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
function AnalysisModeFieldset({
  analysisMode,
  onAnalysisModeChange,
  breakdownAvailable,
  legend = "这次要哪一种",
}: {
  analysisMode: WholeBookAnalysisMode;
  onAnalysisModeChange: (next: WholeBookAnalysisMode) => void;
  breakdownAvailable: boolean;
  legend?: string;
}) {
  return (
    <fieldset className="wbv2-mode" data-testid="whole-book-v2-mode">
      <legend>{legend}</legend>
      {ANALYSIS_MODES.map((item) => {
        // 拆文 exists only in the long-novel engine, and the panel knows which engine this
        // book gets. Offering it on a book that cannot run it would take the money and hand
        // back a diagnostic — an option that cannot be honoured must not look available.
        const unavailable = item.value === "story_breakdown" && !breakdownAvailable;
        return (
          <label
            key={item.value}
            data-selected={item.value === analysisMode}
            data-unavailable={unavailable || undefined}
          >
            <input
              type="radio"
              name="whole-book-analysis-mode"
              value={item.value}
              checked={item.value === analysisMode}
              disabled={unavailable}
              onChange={() => onAnalysisModeChange(item.value)}
            />
            <b>{item.label}</b>
            <span>
              {item.hint}
              {unavailable ? "（本书暂不可用：需先确认作品画像，且章节数不少于 4）" : ""}
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}
function ReanalyseConfirmPanel({
  prepare,
  consented,
  onConsent,
  forceFull,
  onForceFull,
  canConfirm,
  confirming,
  onCancel,
  onConfirm,
  actionError,
  limits,
  onLimitsChange,
  limitGaps,
  analysisMode,
  onAnalysisModeChange,
}: {
  prepare: WholeBookPrepareResponse;
  consented: boolean;
  onConsent: (v: boolean) => void;
  forceFull: boolean;
  onForceFull: (v: boolean) => void;
  canConfirm: boolean;
  confirming: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  actionError: string | null;
  limits: LimitsState;
  onLimitsChange: (next: LimitsState) => void;
  limitGaps: ReturnType<typeof compareLimitsToEstimate>;
  analysisMode: WholeBookAnalysisMode;
  onAnalysisModeChange: (next: WholeBookAnalysisMode) => void;
}) {
  const est = prepare.estimate;
  const provider = est?.provider_name ?? prepare.active_provider_name ?? "—";
  const model = est?.model_name ?? prepare.active_model_name ?? "—";
  const breakdownAvailable = prepare.planner === "long_novel_engine";

  return (
    <section className="wbv2-reanalyse-confirm" data-testid="whole-book-v2-reanalyse-confirm">
      <h2>确认重新分析 V2</h2>
      <p>
        重新分析会创建新的 V2 分析任务。当前分析结果不会立即删除。新分析成功后将显示最新结果。
      </p>
      {/* Defaulted to the reading this book already has, so 重新分析 repeats what is on screen
          unless the person deliberately changes it. This is also the only place to switch a
          book from 评测 to 拆文 or back once it has a result. */}
      <AnalysisModeFieldset
        analysisMode={analysisMode}
        onAnalysisModeChange={onAnalysisModeChange}
        breakdownAvailable={breakdownAvailable}
        legend="这次要哪一种"
      />
      <dl className="wbv2-reanalyse-meta">
        <div>
          <dt>模型服务商</dt>
          <dd>{provider}</dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd>{model}</dd>
        </div>
        <div>
          <dt>章节</dt>
          <dd>{prepare.chapter_count}</dd>
        </div>
        <div>
          <dt>字数</dt>
          <dd>{prepare.character_count.toLocaleString()}</dd>
        </div>
        {est ? (
          <>
            <div>
              <dt>预计窗口</dt>
              <dd>{est.estimated_windows ?? "—"}</dd>
            </div>
            <div>
              <dt>预计调用</dt>
              <dd>{est.estimated_provider_calls ?? "—"}</dd>
            </div>
            <div>
              <dt>预计 tokens</dt>
              <dd>
                {est.estimated_input_tokens ?? "—"} 输入 / {est.estimated_output_tokens ?? "—"} 输出
              </dd>
            </div>
            <div>
              <dt>预计费用</dt>
              <dd>
                {est.estimated_cost_min_cny && est.estimated_cost_max_cny
                  ? `约 ¥${est.estimated_cost_min_cny}～¥${est.estimated_cost_max_cny}`
                  : "—"}
              </dd>
            </div>
          </>
        ) : null}
        {prepare.context_safe != null ? (
          <div>
            <dt>上下文安全</dt>
            <dd>{prepare.context_safe ? "是" : "否"}</dd>
          </div>
        ) : null}
      </dl>
      <LimitsInputs limits={limits} onLimitsChange={onLimitsChange} limitGaps={limitGaps} />
      <label className="wbv2-consent">
        <input
          type="checkbox"
          data-testid="whole-book-v2-force-full"
          checked={forceFull}
          onChange={(e) => onForceFull(e.target.checked)}
        />
        强制重新分析全部 AI 中间结果
      </label>
      <label className="wbv2-consent">
        <input type="checkbox" checked={consented} onChange={(e) => onConsent(e.target.checked)} />
        {REANALYSE_CONSENT_TEXT}
      </label>
      {actionError ? <p className="wbv2-error">{actionError}</p> : null}
      <div className="wbv2-reanalyse-actions">
        <button type="button" className="wbv2-btn-secondary" onClick={onCancel} disabled={confirming}>
          取消
        </button>
        <button type="button" disabled={!canConfirm} onClick={onConfirm}>
          {confirming ? "创建任务中…" : "确认开始重新分析"}
        </button>
      </div>
    </section>
  );
}

/** 第一条进度写下来之前，接口本来就会答「还没有」。
 *
 *  这不是故障，是这一步的正常开头：任务刚创建，切章、规划窗口都还没跑完，一条进度也还没
 *  写。而页面把它画成了红色感叹号加「无法读取数据」——用户看见的是「失败了」，于是去关
 *  程序、去重开、来问我是不是坏了。
 *
 *  所以这一条单独认：它出现时显示「正在启动」，并继续轮询。但也不能永远转下去——真的死在
 *  启动阶段的任务必须露出来，所以过了宽限期还是这一条，就照常报错。 */
const PROGRESS_NOT_READY = "WHOLE_BOOK_V2_PROGRESS_NOT_FOUND";
/** 启动阶段的宽限期。1299 章的书光切章规划就要几十秒，60 秒偏紧，90 秒够而不至于让一个
 *  真死掉的任务藏太久。 */
const STARTUP_GRACE_MS = 90_000;

export function isNotReadyYet(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.code === PROGRESS_NOT_READY || error.status === 404;
}

/** 该给用户看哪一屏。抽成纯函数是因为这里的判断比它看起来难：
 *  「还没有进度」和「出事了」在接口上都是一个非 200，分错了用户就会去关程序。 */
export function progressPanelState(input: {
  isLoading: boolean;
  hasData: boolean;
  error: unknown;
  everHadData: boolean;
  waitedMs: number;
}): "loading" | "starting" | "error" | "ready" {
  if (input.isLoading) return "loading";
  if (input.hasData) return "ready";
  // 已经见过进度之后再读不到，就不是启动问题了，别再拿启动态盖住它。
  if (input.everHadData) return "error";
  if (input.waitedMs < STARTUP_GRACE_MS && isNotReadyYet(input.error)) return "starting";
  return "error";
}

function ProgressPanel({ runId }: { runId: number }) {
  const progressQuery = useQuery({
    queryKey: ["whole-book-v2-progress", runId],
    queryFn: () => getWholeBookV2Progress(runId),
    refetchInterval: 2000,
  });
  // 这一面板挂上的时刻，就是「等第一条进度」的起点。换任务重新计时。
  const waitingSinceRef = useRef<{ runId: number; at: number }>({ runId, at: Date.now() });
  if (waitingSinceRef.current.runId !== runId) {
    waitingSinceRef.current = { runId, at: Date.now() };
  }
  const everHadData = useRef(false);
  if (progressQuery.data) everHadData.current = true;

  const view = progressPanelState({
    isLoading: progressQuery.isLoading,
    hasData: Boolean(progressQuery.data),
    error: progressQuery.error,
    everHadData: everHadData.current,
    waitedMs: Date.now() - waitingSinceRef.current.at,
  });

  if (view === "loading") {
    return (
      <section className="wbv2-state">
        <h1>读取 V2 进度…</h1>
        <Loading />
      </section>
    );
  }
  if (view === "starting") {
    return (
      <section className="wbv2-state" data-testid="whole-book-v2-progress-starting">
        <h1>正在启动分析…</h1>
        <p>正在切分章节、规划窗口。第一条进度出来之前这里会是空的，这一步通常要一分钟。</p>
        <Loading />
      </section>
    );
  }
  if (view === "error" || !progressQuery.data) {
    return <ErrorState error={progressQuery.error ?? new Error("进度不可用")} />;
  }

  const p = progressQuery.data;
  const stageLabel = V2_PROGRESS_LABELS[p.current_stage] || p.current_action;

  return (
    <section className="wbv2-state" data-testid="whole-book-v2-progress">
      <h1>{p.overall_percent.toFixed(0)}%</h1>
      <p>
        {stageLabel} · 阶段 {p.stage_percent.toFixed(0)}%
      </p>
      <p>{p.current_action}</p>
      <p>
        第 {p.current_chapter}/{p.total_chapters} 章 · 窗口 {p.current_window}/{p.total_windows}
      </p>
      <p>
        调用 {p.provider_calls_completed}/{p.provider_calls_estimated} · 已用 {p.elapsed_seconds}s
        {p.estimated_remaining_seconds > 0 ? ` · 预计剩余 ${p.estimated_remaining_seconds}s` : ""}
      </p>
      <p>
        {p.provider} · {p.model}
      </p>
    </section>
  );
}

function RunningWithOldBanner({
  subview,
  onSubviewChange,
}: {
  subview: RunningSubview;
  onSubviewChange: (v: RunningSubview) => void;
}) {
  return (
    <div className="wbv2-reanalyse-running-banner" data-testid="whole-book-v2-reanalyse-running-banner">
      <p>新的 V2 分析正在进行</p>
      <div className="wbv2-reanalyse-running-actions">
        <button
          type="button"
          className={subview === "progress" ? "active" : ""}
          onClick={() => onSubviewChange("progress")}
        >
          查看分析进度
        </button>
        <button
          type="button"
          className={subview === "old-result" ? "active" : ""}
          onClick={() => onSubviewChange("old-result")}
        >
          查看当前旧结果
        </button>
      </div>
    </div>
  );
}

function LegacyNotice({ onReanalyze }: { onReanalyze: () => void }) {
  return (
    <section className="wbv2-state wbv2-legacy" data-testid="whole-book-v2-legacy-notice">
      <h1>旧版分析结果</h1>
      <p>这是旧版全书分析结果，需要重新分析以生成 V2 完整结果。</p>
      <button type="button" onClick={onReanalyze}>
        重新分析
      </button>
    </section>
  );
}

function WholeBookV2ProductPageEnabled() {
  const { bookId: bookIdParam } = useParams();
  const bookId = Number(bookIdParam);
  const queryClient = useQueryClient();
  const realProviderFlagOn = isWholeBookRealProviderEnabled();
  const [activeModule, setActiveModule] = useState<ModuleKey>("overview");
  const [consented, setConsented] = useState(false);
  // The profile gates this page too (10_ADAPTIVE_PROFILE_LAYER §4.3). Read on mount so the
  // requirement is visible before the click, with the 409 kept as the backstop.
  const [profileConfirmed, setProfileConfirmed] = useState<boolean | null>(null);
  useEffect(() => {
    if (!bookId || bookId <= 0) return;
    let cancelled = false;
    void (async () => {
      try {
        const { getBookProfile } = await import("../bookProfile/api");
        const profile = await getBookProfile(bookId);
        if (!cancelled) setProfileConfirmed(profile?.status === "confirmed");
      } catch {
        // Unreadable is not unconfirmed; leave the gate unasserted.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bookId]);
  const [reanalyseConsented, setReanalyseConsented] = useState(false);
  const [forceFullReanalysis, setForceFullReanalysis] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [modeOverride, setModeOverride] = useState<PageMode | null>(null);
  const [runningSubview, setRunningSubview] = useState<RunningSubview>("progress");
  const [limits, setLimits] = useState<LimitsState>({
    max_provider_calls: "",
    max_input_tokens: "",
    max_output_tokens: "",
    max_cost_budget_cny: "",
  });
  const createRequestIdRef = useRef<string | null>(null);
  const reanalysePreviousRunIdRef = useRef<number | null>(null);

  const activeCloudQuery = useQuery({
    queryKey: ["active-cloud-provider"],
    queryFn: settingsApi.activeCloudProvider,
    refetchOnMount: "always",
    staleTime: 0,
  });
  const activeProviderName = activeCloudQuery.data?.provider_name ?? "unknown";

  // In the query key because the panel's headline numbers are mode-dependent: quoting the
  // diagnostic's eight bounded calls for a 拆文 run overstates it by four on every book.
  const [analysisMode, setAnalysisMode] = useState<WholeBookAnalysisMode>("diagnostic");

  const prepareQuery = useQuery({
    queryKey: ["whole-book-v2-prepare", bookId, activeProviderName, analysisMode],
    queryFn: () => wholeBookFreeProductApi.prepare(bookId, analysisMode),
    enabled: bookId > 0 && Boolean(activeCloudQuery.data?.provider_name),
    retry: false,
    // The estimate depends on which reading is selected, so the key carries the mode — but a
    // key change must not blank the page. Without this, picking the other reading throws the
    // whole report away and shows 「正在载入…」 until the estimate comes back.
    placeholderData: (previous) => previous,
    refetchInterval: (query) => {
      const prepare = query.state.data;
      if (!prepare) return false;
      const active = resolveActiveRun(prepare);
      return active ? 3000 : false;
    },
  });

  const prepare = prepareQuery.data;
  const activeRun = prepare ? resolveActiveRun(prepare) : null;
  const completedV2Run = prepare ? resolveCompletedV2Run(prepare) : null;
  // 「读懂」的结果在自己的口上。用 v2 那个口去读它只会拿到 404——它们回答的不是同一个问题。
  // 404 在这里是正常答案（这本书用的是别的读法），所以不重试、也不当错误显示。
  const comprehendQuery = useQuery({
    queryKey: ["whole-book-comprehend", completedV2Run?.run_id ?? null],
    queryFn: () => getComprehendResult(Number(completedV2Run?.run_id)),
    enabled: completedV2Run?.run_id != null,
    retry: false,
  });
  const latestFailedRun = prepare ? resolveLatestFailedRun(prepare) : null;
  const nonRealCompletedRun = prepare ? resolveNonRealCompletedRun(prepare) : null;
  const activeRunId = activeRun?.run_id ?? null;
  // Which reading the reader is looking at. A book can hold both a 评测 and a 拆文; the page
  // used to show whichever finished last and give the other one no entry at all — analysis
  // that was paid for, stored, and unreachable.
  const readings = prepare?.completed_v2_runs_by_reading ?? {};
  const availableReadings = ANALYSIS_MODES.filter((m) => readings[m.value]?.run_id != null);
  const [viewReading, setViewReading] = useState<WholeBookAnalysisMode | null>(null);
  const shownReading =
    viewReading && readings[viewReading]?.run_id != null ? viewReading : null;
  const defaultReading =
    (ANALYSIS_MODES.find((m) => readings[m.value]?.run_id === completedV2Run?.run_id)?.value ??
      null);
  const displayV2RunId =
    (shownReading ? readings[shownReading]?.run_id ?? null : null) ??
    completedV2Run?.run_id ??
    (latestFailedRun ? nonRealCompletedRun?.run_id ?? null : nonRealCompletedRun?.run_id ?? null);
  const hasOldResultWhileRunning = activeRunId != null && displayV2RunId != null;

  const v2ResultQuery = useQuery({
    queryKey: ["whole-book-v2-result", displayV2RunId],
    queryFn: () => getWholeBookV2(displayV2RunId!),
    enabled: displayV2RunId != null,
    retry: false,
  });

  // Seed the selector from the reading this book already has, once, and only until the
  // person touches it. Without this, 重新分析 offers 评测 on a book whose report is 拆文 —
  // and before the selector existed on that panel it simply re-ran as 评测 without asking.
  const modeTouched = useRef(false);
  useEffect(() => {
    if (modeTouched.current) return;
    const doc = v2ResultQuery.data;
    if (!doc) return;
    if (doc.story_breakdown?.four_beats?.length) setAnalysisMode("story_breakdown");
  }, [v2ResultQuery.data]);

  const chooseAnalysisMode = useCallback((next: WholeBookAnalysisMode) => {
    modeTouched.current = true;
    setAnalysisMode(next);
  }, []);

  const invalidateAll = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-prepare", bookId] });
    if (displayV2RunId != null) {
      await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-result", displayV2RunId] });
    }
    if (activeRunId != null) {
      await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-progress", activeRunId] });
    }
  }, [activeRunId, bookId, displayV2RunId, queryClient]);

  const createMutation = useMutation({
    mutationFn: (opts?: { reanalyse?: boolean; previousRunId?: number | null }) => {
      createRequestIdRef.current = newWholeBookClientRequestId("wb-v2");
      const isReanalyse = Boolean(opts?.reanalyse);
      return wholeBookFreeProductApi.createRun(bookId, {
        client_request_id: createRequestIdRef.current,
        estimate_id: prepareQuery.data?.estimate?.estimate_id ?? null,
        max_provider_calls: limits.max_provider_calls ? Number(limits.max_provider_calls) : null,
        max_input_tokens: limits.max_input_tokens ? Number(limits.max_input_tokens) : null,
        max_output_tokens: limits.max_output_tokens ? Number(limits.max_output_tokens) : null,
        max_cost_budget_cny: limits.max_cost_budget_cny || null,
        reanalyse: isReanalyse,
        force_full_reanalysis: isReanalyse ? forceFullReanalysis : false,
        previous_run_id: isReanalyse ? (opts?.previousRunId ?? null) : null,
        analysis_mode: analysisMode,
      });
    },
    onSuccess: () => {
      createRequestIdRef.current = null;
      reanalysePreviousRunIdRef.current = null;
      setActionError(null);
      setModeOverride(null);
      setRunningSubview("progress");
      setReanalyseConsented(false);
      setForceFullReanalysis(false);
      void invalidateAll();
    },
    onError: (err) => {
      createRequestIdRef.current = null;
      if (err instanceof ApiError) {
        setActionError(mapWholeBookStartError(err.code, err.message, err.detail));
        return;
      }
      setActionError("创建分析任务失败");
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (runId: number) => wholeBookFreeProductApi.resumeFailedRun(bookId, runId),
    onSuccess: () => {
      setActionError(null);
      setModeOverride(null);
      setRunningSubview("progress");
      void invalidateAll();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setActionError(mapWholeBookStartError(err.code, err.message, err.detail));
        return;
      }
      setActionError("继续分析失败");
    },
  });

  useEffect(() => {
    const rec = prepareQuery.data?.recommended_limits;
    if (!rec) return;
    setLimits((prev) => ({
      max_provider_calls:
        prev.max_provider_calls || (rec.max_provider_calls != null ? String(rec.max_provider_calls) : ""),
      max_input_tokens:
        prev.max_input_tokens || (rec.max_input_tokens != null ? String(rec.max_input_tokens) : ""),
      max_output_tokens:
        prev.max_output_tokens || (rec.max_output_tokens != null ? String(rec.max_output_tokens) : ""),
      max_cost_budget_cny: prev.max_cost_budget_cny || rec.max_cost_budget_cny || "10.00",
    }));
  }, [prepareQuery.data?.recommended_limits]);

  useEffect(() => {
    if (!activeRun && modeOverride === null) {
      setRunningSubview("progress");
    }
  }, [activeRun, modeOverride]);

  if (bookId <= 0) {
    return <ErrorState error={new Error("无效的书籍 ID")} />;
  }

  if (prepareQuery.isLoading || activeCloudQuery.isLoading) {
    return (
      <section className="wbv2-state" data-testid="whole-book-v2-formal-page">
        <h1>准备全书分析…</h1>
        <Loading />
      </section>
    );
  }

  if (prepareQuery.isError) {
    const err = prepareQuery.error;
    const offline =
      err instanceof ApiError &&
      (err.code === "BACKEND_OFFLINE" || /无法连接本地分析服务/.test(err.message));
    return (
      <ErrorState
        error={
          offline
            ? new Error("本地分析服务暂时不可用。请点击重新连接。")
            : err instanceof Error
              ? err
              : new Error("准备失败")
        }
        retry={() => void prepareQuery.refetch()}
      />
    );
  }

  if (!prepare) {
    return <ErrorState error={new Error("准备数据不可用")} />;
  }

  const pageMode: PageMode = (() => {
    if (modeOverride === "reanalyse-confirm") return "reanalyse-confirm";
    if (activeRun) {
      if (isFailedRun(activeRun.status)) return "failed";
      return "running";
    }
    // New run failed → never auto-restore scaffold as "分析完成".
    if (latestFailedRun && !completedV2Run) return "failed";
    if (!completedV2Run && !activeRun && !nonRealCompletedRun) return "prepare";
    if (completedV2Run) {
      // 「读懂」按设计就没有 V2 结果——那个 404 是正确答案，不是「这是旧版结果」的信号。
      // 不先认它，一次成功的读懂会被判成 legacy，页面请用户「重新分析以生成 V2 完整结果」，
      // 而那份读懂报告好端端地躺在库里。
      if (comprehendQuery.data) return "completed-v2";
      if (comprehendQuery.isLoading || comprehendQuery.isFetching) return "completed-v2";
      if (v2ResultQuery.isSuccess && v2ResultQuery.data) return "completed-v2";
      if (v2ResultQuery.isError && isLegacyV2Error(v2ResultQuery.error)) return "legacy";
      if (v2ResultQuery.isLoading || v2ResultQuery.isFetching) return "completed-v2";
      if (v2ResultQuery.isError) return "failed";
      return "legacy";
    }
    if (nonRealCompletedRun) return "legacy";
    return "prepare";
  })();

  const limitGaps = compareLimitsToEstimate(prepare.estimate, limits);
  const canStart =
    consented &&
    realProviderFlagOn &&
    Boolean(prepare.run_creation_enabled) &&
    Boolean(prepare.provider_available !== false) &&
    limitGaps.length === 0 &&
    !createMutation.isPending;

  const canConfirmReanalyse =
    reanalyseConsented &&
    realProviderFlagOn &&
    Boolean(prepare.run_creation_enabled) &&
    Boolean(prepare.provider_available !== false) &&
    limitGaps.length === 0 &&
    !createMutation.isPending;

  const resumable = prepare.resumable_checkpoint;
  const canResumeFailed =
    Boolean(resumable?.can_resume) &&
    Boolean(resumable?.run_id) &&
    realProviderFlagOn &&
    !resumeMutation.isPending &&
    !createMutation.isPending;

  const openReanalyseConfirm = () => {
    setActionError(null);
    setReanalyseConsented(false);
    setForceFullReanalysis(false);
    setModeOverride("reanalyse-confirm");
  };

  const cancelReanalyseConfirm = () => {
    setActionError(null);
    setModeOverride(null);
  };

  const confirmReanalyse = () => {
    const previousRunId =
      completedV2Run?.run_id ?? nonRealCompletedRun?.run_id ?? displayV2RunId;
    reanalysePreviousRunIdRef.current = previousRunId;
    createMutation.mutate({ reanalyse: true, previousRunId });
  };

  const showRunningProgress =
    pageMode === "running" && (runningSubview === "progress" || !hasOldResultWhileRunning);
  const showOldResultWhileRunning =
    pageMode === "running" && hasOldResultWhileRunning && runningSubview === "old-result";

  return (
    <div className="wbv2-product" data-testid="whole-book-v2-formal-page">
      <header className="wbv2-product-header">
        <p className="muted">
          <Link to={`/books/${bookId}`}>← 返回书籍</Link>
        </p>
        <h1>{PAGE_TITLE}</h1>
        <p className="muted">{PAGE_DESCRIPTION}</p>
        <AnalysisFormSwitch bookId={bookId} />
        {/* The book's title, chapters and length are stated once, by the report's own header
            band below. Repeating them here also printed a *different* word count — 27,766
            (paragraph text) against the report's 28,768 (chapter text, which counts title
            lines and newlines). Both are defensible measurements; showing both under the same
            label 「字数」, two hundred pixels apart, is not. */}
        {/* The confirmation page had no way in: the route existed and nothing linked to it,
            so the only way to reach it was to type the URL. That matters more than a missing
            link usually does — the profile decides which engine analyses the book, so an
            unreachable page meant an unreachable engine. */}
        <p className="muted">
          <Link
            to={profileHref(bookId, { from: "whole-book" })}
            data-testid="whole-book-v2-profile-link"
          >
            作品画像 · 确认后由长篇引擎分析 →
          </Link>
        </p>
      </header>

      {pageMode === "prepare" && (
        <PreparePanel
          prepare={prepare}
          consented={consented}
          onConsent={setConsented}
          canStart={canStart}
          starting={createMutation.isPending}
          analysisMode={analysisMode}
          onAnalysisModeChange={chooseAnalysisMode}
          onStart={() => createMutation.mutate(undefined)}
          actionError={actionError}
          limits={limits}
          onLimitsChange={setLimits}
          limitGaps={limitGaps}
          profileConfirmed={profileConfirmed}
          bookId={bookId}
        />
      )}

      {pageMode === "reanalyse-confirm" && (
        <ReanalyseConfirmPanel
          prepare={prepare}
          consented={reanalyseConsented}
          onConsent={setReanalyseConsented}
          forceFull={forceFullReanalysis}
          onForceFull={setForceFullReanalysis}
          canConfirm={canConfirmReanalyse}
          confirming={createMutation.isPending}
          onCancel={cancelReanalyseConfirm}
          onConfirm={confirmReanalyse}
          actionError={actionError}
          limits={limits}
          onLimitsChange={setLimits}
          limitGaps={limitGaps}
          analysisMode={analysisMode}
          onAnalysisModeChange={chooseAnalysisMode}
        />
      )}

      {pageMode === "running" && hasOldResultWhileRunning && (
        <RunningWithOldBanner subview={runningSubview} onSubviewChange={setRunningSubview} />
      )}

      {showRunningProgress && activeRunId != null && <ProgressPanel runId={activeRunId} />}

      {pageMode === "legacy" && <LegacyNotice onReanalyze={openReanalyseConfirm} />}

      {pageMode === "failed" && (
        <section className="wbv2-state" data-testid="whole-book-v2-failed">
          <h1>分析失败</h1>
          <p>
            阶段：{latestFailedRun?.current_stage_code || activeRun?.current_stage_code || "—"}
          </p>
          <p>
            错误码：
            {latestFailedRun?.failure_code ||
              activeRun?.failure_code ||
              (v2ResultQuery.error instanceof ApiError ? v2ResultQuery.error.code : null) ||
              "—"}
          </p>
          <p>
            {latestFailedRun?.failure_message_safe ||
              activeRun?.failure_message_safe ||
              (v2ResultQuery.error instanceof Error
                ? v2ResultQuery.error.message
                : "全书分析任务失败，可重新分析。")}
          </p>
          {canResumeFailed && (
            <>
              <p className="muted" data-testid="whole-book-v2-resume-hint">
                {resumable?.message ||
                  `已完成 ${resumable?.completed_windows ?? "—"}/${resumable?.total_windows ?? "—"} 个分析窗口，将从失败阶段继续，不会重复已成功的窗口调用。`}
              </p>
              <button
                type="button"
                data-testid="whole-book-v2-resume"
                disabled={resumeMutation.isPending}
                onClick={() => resumeMutation.mutate(Number(resumable!.run_id))}
              >
                {resumeMutation.isPending ? "继续中…" : "继续分析"}
              </button>
            </>
          )}
          <button type="button" onClick={openReanalyseConfirm}>
            {canResumeFailed ? "重新分析全部" : "重新分析"}
          </button>
          {actionError && <p className="wbv2-error">{actionError}</p>}
        </section>
      )}

      {(pageMode === "completed-v2" || showOldResultWhileRunning) && comprehendQuery.data && (
        <ComprehendReportView
          data={comprehendQuery.data}
          title={String(prepare?.book_title ?? "")}
          runId={completedV2Run?.run_id ?? null}
        />
      )}

      {(pageMode === "completed-v2" || showOldResultWhileRunning) &&
        !comprehendQuery.data &&
        v2ResultQuery.data && (
        <WholeBookV2ReportView
          data={v2ResultQuery.data}
          activeModule={activeModule}
          onModuleChange={setActiveModule}
          mode="formal"
          bookId={bookId}
          showReanalyzeButton={pageMode === "completed-v2" && !activeRun}
          onReanalyzeClick={openReanalyseConfirm}
          analysisStatusLabel={showOldResultWhileRunning ? "当前旧结果" : undefined}
          headerExtra={
            <ReadingSwitch
              readings={availableReadings}
              current={shownReading ?? defaultReading}
              onChange={setViewReading}
            />
          }
        />
      )}

      {(pageMode === "completed-v2" || showOldResultWhileRunning) &&
        !v2ResultQuery.data &&
        v2ResultQuery.isLoading && (
          <section className="wbv2-state">
            <h1>加载 V2 报告…</h1>
            <Loading />
          </section>
        )}

      {pageMode === "failed" && (completedV2Run || nonRealCompletedRun) && v2ResultQuery.data && (
        <WholeBookV2ReportView
          data={v2ResultQuery.data}
          activeModule={activeModule}
          onModuleChange={setActiveModule}
          mode="formal"
          bookId={bookId}
          showReanalyzeButton
          onReanalyzeClick={openReanalyseConfirm}
          analysisStatusLabel="当前旧结果"
          headerBanner={
            <div className="wbv2-error-banner">
              {nonRealCompletedRun && !completedV2Run
                ? "最新分析失败。当前旧结果不是完整真实 V2 分析，需要重新分析。"
                : "新的分析任务失败。您可以查看当前旧结果，或再次尝试重新分析。"}
            </div>
          }
        />
      )}
    </div>
  );
}

export function WholeBookV2ProductPage() {
  if (!isWholeBookFreeProductEnabled()) {
    return <ProductUnavailable />;
  }
  return <WholeBookV2ProductPageEnabled />;
}
