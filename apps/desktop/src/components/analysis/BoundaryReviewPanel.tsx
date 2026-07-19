import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { ApiError } from "../../services/apiClient";
import { Badge, Empty, ErrorState, Loading } from "../common/States";

type ConfirmState =
  | "idle"
  | "validating"
  | "blocked"
  | "confirming"
  | "confirmed"
  | "failed";

type TimelineGap = {
  gap_after_paragraph_id: string;
  paragraph_index: number;
  transition_id: string | null;
  decision_id: number | null;
  source: "model_candidate" | "semantic_conflict" | "manual_added" | "none";
  status: string;
  review_priority: string | null;
  decision: any | null;
};

function decisionKey(item: any): string {
  if (item.user_decision === "manually_added" || !item.model_candidate) {
    return `manual-${item.id ?? item.transition_id}`;
  }
  return `decision-${item.id ?? item.transition_id}`;
}

function priorityRank(value: string) {
  return ({ high: 0, medium: 1, low: 2 } as Record<string, number>)[value] ?? 3;
}

function sortDecisions(decisions: any[]) {
  return [...decisions].sort((a, b) => {
    const aConflict = a.semantic_conflict ? 0 : 1;
    const bConflict = b.semantic_conflict ? 0 : 1;
    if (aConflict !== bConflict) return aConflict - bConflict;
    const aManual = a.user_decision === "manually_added" || !a.model_candidate ? 1 : 0;
    const bManual = b.user_decision === "manually_added" || !b.model_candidate ? 1 : 0;
    if (aManual !== bManual) return aManual - bManual;
    const byPriority = priorityRank(a.review_priority) - priorityRank(b.review_priority);
    if (byPriority !== 0) return byPriority;
    return String(a.transition_id).localeCompare(String(b.transition_id));
  });
}

export function BoundaryReviewPanel({
  bookId,
  chapterId,
  onConfirmed,
}: {
  bookId: number;
  chapterId: number;
  onConfirmed?: (result: {
    runId: number | null;
    revisionId: number;
    budgetBlocked: boolean;
  }) => void;
}) {
  const qc = useQueryClient();
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ id: string; previous: string }[]>([]);
  const [stage2, setStage2] = useState<any>(null);
  const [confirmState, setConfirmState] = useState<ConfirmState>("idle");
  const [conflictAccepting, setConflictAccepting] = useState<string | null>(null);
  const [manualReasons, setManualReasons] = useState<Record<string, string>>({});
  const [manualNotes, setManualNotes] = useState<Record<string, string>>({});
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [batchAcceptConfirmOpen, setBatchAcceptConfirmOpen] = useState(false);
  const [batchAcceptBusy, setBatchAcceptBusy] = useState(false);
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  const cardRefs = useRef<Record<string, HTMLElement | null>>({});

  const query = useQuery({
    queryKey: ["boundary-review", bookId, chapterId],
    queryFn: () => analysisApi.boundaryReview(bookId, chapterId),
    retry: false,
  });
  useEffect(() => {
    if (query.data?.status === "confirmed") {
      setConfirmState("confirmed");
      setMessage((current) =>
        current.includes("尚未处理") || current.includes("BOUNDARY_REVIEW")
          ? "边界审阅已确认。"
          : current || "边界审阅已确认。",
      );
    }
  }, [query.data?.status]);
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["boundary-review", bookId, chapterId] });
  };
  const decide = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) => {
      if (query.data?.status === "confirmed") {
        return Promise.reject(new Error("已确认审阅不可再编辑"));
      }
      return analysisApi.decideBoundary(query.data!.id, id, value);
    },
    onSuccess: refresh,
    onError: (error: Error) => setMessage(error.message),
  });
  const review = query.data;
  const ordered = useMemo(() => sortDecisions(review?.decisions || []), [review]);
  const pendingItems = useMemo(
    () =>
      (review?.decisions || []).filter(
        (item: any) => item.model_candidate && item.user_decision === "pending",
      ),
    [review],
  );
  const pendingNonConflictItems = useMemo(
    () => pendingItems.filter((item: any) => !item.semantic_conflict),
    [pendingItems],
  );
  const pendingConflictItems = useMemo(
    () => pendingItems.filter((item: any) => item.semantic_conflict),
    [pendingItems],
  );
  const conflictCount = useMemo(
    () => (review?.decisions || []).filter((item: any) => item.semantic_conflict).length,
    [review],
  );
  const positions = useMemo(
    () => new Map(review?.paragraphs.map((item: any, index: number) => [item.id, index]) || []),
    [review],
  );
  const gaps: TimelineGap[] = useMemo(() => {
    if (!review) return [];
    return review.paragraphs.map((paragraph: any, index: number) => {
      const decision =
        review.decisions.find((item: any) => item.left_paragraph_id === paragraph.id) || null;
      let source: TimelineGap["source"] = "none";
      if (decision) {
        if (decision.user_decision === "manually_added" || !decision.model_candidate) {
          source = "manual_added";
        } else if (decision.semantic_conflict) {
          source = "semantic_conflict";
        } else {
          source = "model_candidate";
        }
      }
      return {
        gap_after_paragraph_id: paragraph.id,
        paragraph_index: index,
        transition_id: decision?.transition_id ?? null,
        decision_id: decision?.id ?? null,
        source,
        status: decision?.user_decision ?? "none",
        review_priority: decision?.review_priority ?? null,
        decision,
      };
    });
  }, [review]);

  useEffect(() => {
    if (!activeKey || !review) return;
    const node = cardRefs.current[activeKey];
    node?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    titleRef.current?.focus();
  }, [activeKey, review]);

  if (query.isLoading) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  if (!review) return <Empty text="当前章节尚无场景边界审阅" />;

  const selectDecision = (item: any) => {
    const key = decisionKey(item);
    setActiveKey(key);
    setConfirmState((current) => (current === "blocked" ? "idle" : current));
  };

  const focusNextPending = (afterTransitionId?: string) => {
    const pending = (query.data?.decisions || review.decisions || []).filter(
      (item: any) => item.model_candidate && item.user_decision === "pending",
    );
    // Prefer freshly ordered pending from current review snapshot.
    const livePending = ordered.filter(
      (item: any) => item.model_candidate && item.user_decision === "pending",
    );
    const list = livePending.length ? livePending : pending;
    if (!list.length) {
      setActiveKey(null);
      return;
    }
    if (afterTransitionId) {
      const index = list.findIndex((item: any) => item.transition_id === afterTransitionId);
      const next = list[index + 1] || list[0];
      selectDecision(next);
      return;
    }
    selectDecision(list[0]);
  };

  const act = async (
    item: any,
    value: string,
    manualReasonType?: string,
    userReason?: string,
  ) => {
    setHistory((current) => [...current, { id: item.transition_id, previous: item.user_decision }]);
    try {
      const updated = await analysisApi.decideBoundary(
        review.id,
        item.transition_id,
        value,
        manualReasonType,
        userReason,
      );
      setMessage("已保存");
      await qc.invalidateQueries({ queryKey: ["boundary-review", bookId, chapterId] });
      if (value === "accept" || value === "reject") {
        const next = sortDecisions(updated?.decisions || []).find(
          (candidate: any) =>
            candidate.model_candidate && candidate.user_decision === "pending",
        );
        if (next) selectDecision(next);
        else setActiveKey(null);
      }
      try {
        const preview = await analysisApi.scenePreview(review.id);
        setStage2((current: any) =>
          current?.estimate
            ? { ...current, preview }
            : current
              ? { ...current, preview }
              : null,
        );
      } catch {
        // preview is optional after each decision
      }
    } catch (error) {
      setMessage((error as Error).message);
    }
  };

  const manual = async (paragraphId: string) => {
    try {
      await analysisApi.addManualBoundary(review.id, paragraphId);
      setMessage("已保存");
      await refresh();
      try {
        const preview = await analysisApi.scenePreview(review.id);
        setStage2((current: any) => (current?.estimate ? { ...current, preview } : current));
      } catch {
        // optional
      }
    } catch (error) {
      setMessage((error as Error).message);
    }
  };

  const loadStage2 = async () => {
    const preview = await analysisApi.scenePreview(review.id);
    const estimate = await analysisApi.sceneAnalysisPreflight(review.id);
    setStage2({ preview, estimate });
    return { preview, estimate };
  };

  const onTimelineClick = (gap: TimelineGap) => {
    if (gap.paragraph_index === review.paragraphs.length - 1) return;
    if (gap.decision) {
      selectDecision(gap.decision);
      return;
    }
    void manual(gap.gap_after_paragraph_id);
  };

  const isConfirmed = review.status === "confirmed" || confirmState === "confirmed";
  const confirmBusy = confirmState === "validating" || confirmState === "confirming";
  const pendingCount = pendingItems.length;
  const canCompleteReview = !isConfirmed && pendingCount === 0 && !confirmBusy;

  const runAcceptAllNonConflicts = async () => {
    if (batchAcceptBusy || isConfirmed) return;
    const targets = pendingNonConflictItems;
    const excludedConflicts = pendingConflictItems.length;
    if (!targets.length) {
      setMessage(
        excludedConflicts
          ? `没有可批量接受的非冲突项；仍有${excludedConflicts}个冲突项需人工处理。`
          : "没有待审的非冲突项。",
      );
      setBatchAcceptConfirmOpen(false);
      return;
    }
    setBatchAcceptBusy(true);
    setMessage(`正在接受${targets.length}个非冲突项……`);
    let accepted = 0;
    try {
      for (const item of targets) {
        await analysisApi.decideBoundary(review.id, item.transition_id, "accept");
        accepted += 1;
      }
      setBatchAcceptConfirmOpen(false);
      setMessage(
        excludedConflicts
          ? `已接受${accepted}个非冲突项；已排除${excludedConflicts}个冲突项，请人工处理。`
          : `已接受${accepted}个非冲突项。`,
      );
      await refresh();
      const fresh = await analysisApi.boundaryReview(bookId, chapterId);
      const nextPending = sortDecisions(fresh?.decisions || []).find(
        (candidate: any) =>
          candidate.model_candidate && candidate.user_decision === "pending",
      );
      if (nextPending) selectDecision(nextPending);
      else setActiveKey(null);
    } catch (error) {
      setBatchAcceptConfirmOpen(false);
      if (error instanceof ApiError) {
        setMessage(
          [
            `批量接受失败（已成功${accepted}/${targets.length}）`,
            error.userActionHint || error.message,
            error.code ? `error_code=${error.code}` : "",
            `HTTP ${error.status}`,
            error.requestId ? `request_id=${error.requestId}` : "",
          ]
            .filter(Boolean)
            .join(" · "),
        );
      } else {
        setMessage(
          `批量接受失败（已成功${accepted}/${targets.length}）：${(error as Error).message}`,
        );
      }
      await refresh();
    } finally {
      setBatchAcceptBusy(false);
    }
  };

  const runConfirm = async () => {
    if (confirmBusy || !canCompleteReview) return;
    setConfirmState("confirming");
    setMessage("正在保存BoundaryRevision并计算Scene Analysis预算……");
    try {
      await loadStage2();
      const result = await analysisApi.confirmReview(review.id, "desktop-user");
      setConfirmState("confirmed");
      const runId =
        Number(review.analysis_run_id || review.run_id || result.analysis_run_id) || null;
      if (result.budget_blocked) {
        setMessage(
          `边界已确认（Revision #${result.revision_id}）。分析已暂停：今日云端请求额度不足。请在本章进度面板调整额度并继续，不会重新识别场景边界。`,
        );
      } else {
        setMessage(
          `本章边界已确认（Revision #${result.revision_id}），Scene Analysis 已在本章进度中继续。`,
        );
      }
      await refresh();
      onConfirmed?.({
        runId,
        revisionId: result.revision_id,
        budgetBlocked: Boolean(result.budget_blocked),
      });
    } catch (error) {
      setConfirmState("failed");
      if (error instanceof ApiError) {
        const pendingIds =
          (error.detail as any)?.pending_transition_ids ||
          (error as any).pendingTransitionIds ||
          [];
        setMessage(
          [
            error.userActionHint || error.message,
            error.code ? `error_code=${error.code}` : "",
            `HTTP ${error.status}`,
            error.requestId ? `request_id=${error.requestId}` : "",
            pendingIds.length ? `pending=${pendingIds.join(", ")}` : "",
          ]
            .filter(Boolean)
            .join(" · "),
        );
        if (pendingIds[0]) {
          const item = review.decisions.find((d: any) => d.transition_id === pendingIds[0]);
          if (item) selectDecision(item);
        }
      } else {
        setMessage((error as Error).message || "完成审阅失败，请重试。");
      }
    }
  };

  return (
    <div className="boundary-review">
      <header className="review-head">
        <div>
          <p className="eyebrow">辅助审阅模式</p>
          <h2 ref={titleRef} tabIndex={-1}>
            场景边界审阅
          </h2>
        </div>
        <Badge tone="warning">{review.status}</Badge>
        <span>
          {review.provider} / {review.model} · Prompt {review.prompt_version}
        </span>
      </header>
      <div className="scene-preview-summary" data-testid="review-stats">
        待审 {pendingItems.length}｜已接受 {review.accepted_count}｜已拒绝 {review.rejected_count}
        ｜人工新增 {review.manually_added_count}｜冲突 {conflictCount}
      </div>
      {message && (
        <p className="notice" data-testid="review-message">
          {message}
        </p>
      )}
      <div className="boundary-timeline" aria-label="章节段落时间线">
        {gaps.map((gap) => {
          const markClass =
            gap.source === "none"
              ? ""
              : `timeline-mark ${gap.status}${gap.source === "semantic_conflict" && gap.status === "pending" ? " pending" : ""}`;
          const isActive =
            gap.decision && activeKey === decisionKey(gap.decision) ? " active" : "";
          return (
            <button
              key={gap.gap_after_paragraph_id}
              type="button"
              className={`${markClass}${isActive}`.trim()}
              disabled={gap.paragraph_index === review.paragraphs.length - 1}
              title={
                gap.transition_id
                  ? `${gap.gap_after_paragraph_id} · ${gap.transition_id}`
                  : gap.gap_after_paragraph_id
              }
              data-testid={
                gap.transition_id ? `timeline-${gap.transition_id}` : `timeline-gap-${gap.paragraph_index + 1}`
              }
              data-transition-id={gap.transition_id || undefined}
              data-source={gap.source}
              onClick={() => onTimelineClick(gap)}
            >
              {gap.paragraph_index + 1}
            </button>
          );
        })}
      </div>
      {stage2?.preview && (
        <div className="scene-preview-summary" data-testid="scene-preview-live">
          Scene预览：{stage2.preview.scenes.length}个，覆盖率
          {(stage2.preview.coverage_rate * 100).toFixed(0)}%
        </div>
      )}
      {stage2?.estimate && (
        <div className="budget-preview" data-testid="stage2-budget-preview">
          <h3>Scene Analysis 预算预览</h3>
          <ul>
            <li>Scene数量：{stage2.preview?.scenes?.length ?? stage2.estimate.scene_count}</li>
            <li>预计请求：{stage2.estimate.expected_request_count}</li>
            <li>最坏请求：{stage2.estimate.worst_case_request_count}</li>
            <li>预计Token：{stage2.estimate.estimated_total_tokens}</li>
            <li>最坏Token：{stage2.estimate.worst_case_total_tokens}</li>
            <li>预计费用：{stage2.estimate.estimated_cost}</li>
            <li>最坏费用：{stage2.estimate.worst_case_cost}</li>
            <li>当前剩余请求：{stage2.estimate.remaining?.requests}</li>
            <li>当前剩余Token：{stage2.estimate.remaining?.tokens}</li>
            <li>当前剩余费用：{stage2.estimate.remaining?.estimated_cost}</li>
          </ul>
          {!stage2.estimate.within_budget && (
            <p>Stage 2预算不足时仍可确认边界；Scene Analysis 将进入可恢复阻塞状态。</p>
          )}
        </div>
      )}
      {ordered.map((item: any) => {
        const key = decisionKey(item);
        const index = positions.get(item.left_paragraph_id) as number;
        const context = review.paragraphs.slice(
          Math.max(0, index - 3),
          Math.min(review.paragraphs.length, index + 5),
        );
        let enumSnapshot: any = {};
        try {
          enumSnapshot = JSON.parse(item.enum_snapshot_json || item.first_pass_json || "{}");
        } catch {
          enumSnapshot = {};
        }
        return (
          <article
            className={`review-candidate${activeKey === key ? " selected" : ""}`}
            key={key}
            data-decision-key={key}
            data-testid={`decision-card-${item.transition_id}`}
            ref={(node) => {
              cardRefs.current[key] = node;
            }}
          >
            <header>
              <Badge tone={item.review_priority === "high" ? "warning" : "neutral"}>
                {item.review_priority}
              </Badge>
              <b>{item.transition_id}</b>
              <span>{item.model_reason_code || "人工新增"}</span>
              <span>置信度 {((item.model_confidence || 0) * 100).toFixed(0)}%</span>
            </header>
            {item.semantic_conflict && (
              <div className="notice" data-testid="semantic-conflict">
                <b>模型与规则发生冲突</b>
                <p>
                  模型认为这里可能是场景边界，但其结构化分类显示行动链仍连续，需要人工判断。
                </p>
                <dl>
                  <dt>Transition ID</dt>
                  <dd>{item.transition_id}</dd>
                  <dt>模型候选</dt>
                  <dd>{item.model_boundary_candidate ? "true" : "false"}</dd>
                  <dt>goal_relation</dt>
                  <dd>{enumSnapshot.goal_relation || "-"}</dd>
                  <dt>action_chain_relation</dt>
                  <dd>{enumSnapshot.action_chain_relation || "-"}</dd>
                  <dt>trigger_type</dt>
                  <dd>{enumSnapshot.trigger_type || "-"}</dd>
                  <dt>deterministic_reason</dt>
                  <dd>{item.deterministic_reason || "null"}</dd>
                  <dt>deterministic_legal</dt>
                  <dd>
                    {item.deterministic_legal === false
                      ? "false"
                      : item.deterministic_legal === true
                        ? "true"
                        : "-"}
                  </dd>
                  <dt>conflict_code</dt>
                  <dd>{item.conflict_code}</dd>
                  <dt>review_priority</dt>
                  <dd>{item.review_priority}</dd>
                  <dt>来源批次</dt>
                  <dd>Batch {item.source_batch_index ?? "-"}</dd>
                </dl>
              </div>
            )}
            <div className="review-context">
              {context.map((paragraph: any) => (
                <div key={paragraph.id}>
                  {paragraph.id === item.right_paragraph_id && (
                    <div className="boundary-divider">候选场景边界</div>
                  )}
                  <small>{paragraph.id}</small>
                  <p>{paragraph.raw_text}</p>
                </div>
              ))}
            </div>
            <details>
              <summary>模型结构化结果</summary>
              <pre>{item.first_pass_json}</pre>
              <pre>{item.adjudication_result}</pre>
            </details>
            <footer>
              {item.model_candidate ? (
                <>
                  <button
                    className="primary"
                    onClick={() => {
                      if (item.semantic_conflict) setConflictAccepting(item.transition_id);
                      else void act(item, "accept");
                    }}
                  >
                    接受边界
                  </button>
                  <button onClick={() => void act(item, "reject")}>拒绝边界</button>
                  <button onClick={() => void act(item, "pending")}>保持待审</button>
                </>
              ) : (
                <button
                  onClick={async () => {
                    await analysisApi.deleteManualBoundary(review.id, item.transition_id);
                    setMessage("已保存");
                    await refresh();
                  }}
                >
                  删除新增边界
                </button>
              )}
              <Badge>{item.user_decision}</Badge>
            </footer>
            {conflictAccepting === item.transition_id && (
              <div className="panel" data-testid="conflict-accept-form">
                <label>
                  人工原因类型
                  <select
                    aria-label="人工原因类型"
                    value={manualReasons[item.transition_id] || ""}
                    onChange={(event) =>
                      setManualReasons((current) => ({
                        ...current,
                        [item.transition_id]: event.target.value,
                      }))
                    }
                  >
                    <option value="">请选择</option>
                    <option value="location_change">location_change</option>
                    <option value="time_jump">time_jump</option>
                    <option value="viewpoint_change">viewpoint_change</option>
                    <option value="primary_goal_reset">primary_goal_reset</option>
                    <option value="explicit_scene_separator">explicit_scene_separator</option>
                    <option value="other_manual_boundary">other_manual_boundary</option>
                  </select>
                </label>
                <label>
                  简短理由
                  <input
                    aria-label="冲突边界人工理由"
                    value={manualNotes[item.transition_id] || ""}
                    onChange={(event) =>
                      setManualNotes((current) => ({
                        ...current,
                        [item.transition_id]: event.target.value,
                      }))
                    }
                  />
                </label>
                <button
                  className="primary"
                  disabled={!manualReasons[item.transition_id]}
                  onClick={() => {
                    void act(
                      item,
                      "accept",
                      manualReasons[item.transition_id],
                      manualNotes[item.transition_id],
                    );
                    setConflictAccepting(null);
                  }}
                >
                  确认人工接受
                </button>
                <button onClick={() => setConflictAccepting(null)}>取消</button>
              </div>
            )}
          </article>
        );
      })}
      <footer className="review-actions">
        <button
          onClick={async () => {
            const last = history.at(-1);
            if (!last) return;
            setHistory((current) => current.slice(0, -1));
            decide.mutate({ id: last.id, value: last.previous });
          }}
          disabled={!history.length}
        >
          撤销上一步
        </button>
        <button onClick={() => setMessage("草稿已保存")}>保存草稿</button>
        <button
          onClick={async () => {
            try {
              const { preview } = await loadStage2();
              setMessage(`Scene预览：${preview.scenes.length}个，覆盖率${preview.coverage_rate * 100}%`);
            } catch (error) {
              setMessage((error as Error).message);
            }
          }}
        >
          Scene预览
        </button>
        {!isConfirmed && (
          <button
            type="button"
            data-testid="accept-all-non-conflicts"
            disabled={batchAcceptBusy || pendingNonConflictItems.length === 0}
            onClick={() => setBatchAcceptConfirmOpen(true)}
          >
            接受全部非冲突项
          </button>
        )}
        {pendingCount > 0 && !isConfirmed && (
          <>
            <span className="notice" data-testid="pending-remaining-hint">
              还有{pendingCount}项待处理
              {pendingConflictItems.length > 0
                ? `（含${pendingConflictItems.length}个冲突项需人工处理）`
                : ""}
            </span>
            <button
              type="button"
              data-testid="locate-next-pending"
              onClick={() => focusNextPending()}
            >
              定位到下一项
            </button>
          </>
        )}
        {batchAcceptConfirmOpen && !isConfirmed && (
          <div className="panel" data-testid="batch-accept-confirm">
            <p>
              将接受 {pendingNonConflictItems.length} 个非冲突待审项；排除{" "}
              {pendingConflictItems.length} 个冲突项（冲突项必须人工处理，不会被批量接受）。
            </p>
            <button
              className="primary"
              data-testid="batch-accept-confirm-yes"
              disabled={batchAcceptBusy || pendingNonConflictItems.length === 0}
              onClick={() => void runAcceptAllNonConflicts()}
            >
              {batchAcceptBusy ? "正在接受……" : "确认接受非冲突项"}
            </button>
            <button
              type="button"
              data-testid="batch-accept-confirm-no"
              disabled={batchAcceptBusy}
              onClick={() => setBatchAcceptConfirmOpen(false)}
            >
              取消
            </button>
          </div>
        )}
        {isConfirmed ? (
          <div className="notice" data-testid="boundary-review-confirmed-status">
            <p>边界审阅已确认。决策不可再编辑。</p>
            {stage2?.revision_id && <p>BoundaryRevision #{stage2.revision_id}</p>}
            {stage2?.scene_count != null && <p>正式Scene：{stage2.scene_count}个</p>}
            <p data-testid="scene-analysis-followup-hint">
              {runStatusHint(review)}
            </p>
          </div>
        ) : (
          <button
            className="primary"
            data-testid="confirm-all-boundaries"
            disabled={!canCompleteReview}
            aria-busy={confirmBusy}
            title={
              pendingCount > 0
                ? `还有${pendingCount}项待处理，处理完毕后可完成审阅`
                : "完成审阅并进入 Scene Analysis"
            }
            onClick={() => void runConfirm()}
          >
            {confirmState === "confirming" ? "正在确认……" : "完成审阅"}
          </button>
        )}
      </footer>
    </div>
  );
}

function runStatusHint(review: any): string {
  const status = review?.run_status || review?.analysis_run_status;
  if (status === "succeeded") return "Scene Analysis已完成，可在本章查看分析结果。";
  if (status === "scene_analysis_running") {
    return "Scene Analysis运行中……请在本章右侧进度面板查看实时进度。";
  }
  if (status === "scene_analysis_partial" || (status === "failed" && review?.failed_stage === "scene_analysis")) {
    return "Scene Analysis未完成，可在本章进度面板恢复同一任务。";
  }
  if (status === "boundary_confirmed_budget_blocked") {
    return "分析已暂停：今日云端请求额度不足。请在本章进度面板调整额度并继续。";
  }
  return "请在本章右侧进度面板查看 Scene Analysis 进度；任务中心仅作全局汇总。";
}
