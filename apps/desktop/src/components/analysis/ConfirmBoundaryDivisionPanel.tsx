/** Confirm-only scene division UI — replaces per-candidate BoundaryReviewPanel for product. */

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { ApiError } from "../../services/apiClient";
import { getBoundaryReviewMode } from "../../services/boundaryReviewMode";
import "./confirmBoundaryDivision.css";

type Props = {
  bookId: number;
  chapterId: number;
  chapterTitle?: string;
  onExit?: () => void;
  onConfirmed?: (result: {
    runId: number | null;
    revisionId: number;
    budgetBlocked: boolean;
  }) => void;
  onReidentify?: () => void;
};

export function ConfirmBoundaryDivisionPanel({
  bookId,
  chapterId,
  chapterTitle,
  onExit,
  onConfirmed,
  onReidentify,
}: Props) {
  const qc = useQueryClient();
  const [error, setError] = useState<string>();
  const [activeScene, setActiveScene] = useState(1);
  const confirmLock = useRef(false);
  const sceneRefs = useRef<Record<number, HTMLElement | null>>({});

  const reviewQuery = useQuery({
    queryKey: ["boundary-review", bookId, chapterId],
    queryFn: () => analysisApi.boundaryReview(bookId, chapterId),
    retry: false,
  });

  const reviewId = reviewQuery.data?.id as number | undefined;
  const proposalQuery = useQuery({
    queryKey: ["final-boundary-proposal", reviewId],
    queryFn: () => analysisApi.finalBoundaryProposal(reviewId!),
    enabled: typeof reviewId === "number",
    retry: false,
  });

  const proposal = proposalQuery.data;
  const paragraphs = proposal?.paragraphs || reviewQuery.data?.paragraphs || [];
  const sceneCount = proposal?.scene_count || 0;
  const title =
    proposal?.chapter_title || chapterTitle || reviewQuery.data?.chapter_title || "本章";

  const sceneBlocks = useMemo(() => {
    type Para = { id: string; raw_text: string; paragraph_index: number };
    type Range = {
      ordinal: number;
      paragraph_ids: string[];
      start_paragraph_id: string;
      end_paragraph_id: string;
    };
    if (!proposal?.final_scene_ranges?.length) return [] as Array<{ ordinal: number; paragraphs: Para[] }>;
    const byId = new Map((paragraphs as Para[]).map((p) => [p.id, p]));
    return (proposal.final_scene_ranges as Range[]).map((range) => ({
      ordinal: range.ordinal,
      paragraphs: (range.paragraph_ids || [])
        .map((id) => byId.get(id))
        .filter((p): p is Para => Boolean(p)),
    }));
  }, [proposal, paragraphs]);

  useEffect(() => {
    if (getBoundaryReviewMode() !== "confirm_only") return;
  }, []);

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!reviewId || !proposal?.proposal_fingerprint) {
        throw new Error("缺少场景划分方案");
      }
      return analysisApi.confirmFinalBoundaryProposal(reviewId, {
        confirmed_by: "user",
        proposal_fingerprint: proposal.proposal_fingerprint,
        client_request_id:
          globalThis.crypto?.randomUUID?.() || `confirm-boundary-${reviewId}-${Date.now()}`,
      });
    },
    onSuccess: (result) => {
      confirmLock.current = false;
      void qc.invalidateQueries({ queryKey: ["boundary-review", bookId, chapterId] });
      onConfirmed?.({
        runId: reviewQuery.data?.analysis_run_id ?? null,
        revisionId: result.revision_id,
        budgetBlocked: Boolean(result.budget_blocked),
      });
    },
    onError: (err) => {
      confirmLock.current = false;
      setError((err as ApiError).message || (err as Error).message || "确认失败");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!reviewId) throw new Error("缺少审阅任务");
      await analysisApi.cancelBoundaryReview(reviewId);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["boundary-review", bookId, chapterId] });
      onExit?.();
    },
    onError: (err) => {
      setError((err as ApiError).message || (err as Error).message || "取消失败");
    },
  });

  const scrollToScene = (ordinal: number) => {
    setActiveScene(ordinal);
    sceneRefs.current[ordinal]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleConfirm = () => {
    if (confirmLock.current || confirmMutation.isPending) return;
    if (proposal?.validation_status !== "valid") return;
    confirmLock.current = true;
    setError(undefined);
    confirmMutation.mutate();
  };

  if (reviewQuery.isLoading || (reviewId && proposalQuery.isLoading)) {
    return (
      <section className="confirm-boundary-panel" data-testid="confirm-boundary-division">
        <p data-testid="confirm-boundary-loading">正在整理场景划分…</p>
      </section>
    );
  }

  if (reviewQuery.isError || !reviewId) {
    return (
      <section className="confirm-boundary-panel" data-testid="confirm-boundary-division">
        <p data-testid="confirm-boundary-missing">当前章节没有待确认的场景划分。</p>
        {onExit && (
          <button type="button" className="secondary" onClick={onExit}>
            返回
          </button>
        )}
      </section>
    );
  }

  if (proposal?.validation_status === "unresolved") {
    return (
      <section className="confirm-boundary-panel" data-testid="confirm-boundary-division">
        <header className="confirm-boundary-head">
          <h1>场景划分未完成</h1>
          <p data-testid="confirm-boundary-unresolved">
            {proposal.unresolved_reason ||
              "当前候选无法形成完整、合法的场景划分，请重新识别。"}
          </p>
        </header>
        <div className="confirm-boundary-actions">
          <button
            type="button"
            className="secondary"
            data-testid="confirm-boundary-cancel"
            disabled={cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
          >
            取消本次分析
          </button>
          <button
            type="button"
            className="primary"
            data-testid="confirm-boundary-reidentify"
            onClick={() => {
              if (
                window.confirm(
                  "重新识别场景边界可能产生新的模型费用。确认继续？",
                )
              ) {
                onReidentify?.();
              }
            }}
          >
            重新识别场景
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className="confirm-boundary-panel"
      data-testid="confirm-boundary-division"
      data-boundary-review-mode="confirm_only"
    >
      <header className="confirm-boundary-head">
        <h1>确认场景划分</h1>
        <p data-testid="confirm-boundary-lead">
          StoryLens 已将本章划分为 {sceneCount} 个场景。请快速浏览后确认继续。
        </p>
        <div className="confirm-boundary-meta" data-testid="confirm-boundary-meta">
          <span data-testid="confirm-boundary-chapter">{title}</span>
          <span data-testid="confirm-boundary-scene-count">建议场景数：{sceneCount}</span>
          <span data-testid="confirm-boundary-paragraph-count">
            正文段落数：{proposal?.paragraph_count ?? paragraphs.length}
          </span>
        </div>
        {sceneCount > 1 && (
          <nav className="confirm-boundary-scene-nav" data-testid="confirm-boundary-scene-nav">
            {sceneBlocks.map((block) => (
              <button
                key={block.ordinal}
                type="button"
                className={activeScene === block.ordinal ? "active" : undefined}
                data-testid={`confirm-boundary-jump-${block.ordinal}`}
                onClick={() => scrollToScene(block.ordinal)}
              >
                场景{block.ordinal}
              </button>
            ))}
          </nav>
        )}
      </header>

      <div className="confirm-boundary-body" data-testid="confirm-boundary-body">
        {sceneBlocks.map((block, index) => (
          <div key={block.ordinal}>
            {index > 0 && (
              <div className="confirm-boundary-divider" data-testid="confirm-boundary-divider">
                ──────── 场景分隔 ────────
              </div>
            )}
            <article
              className="confirm-boundary-scene"
              data-testid={`confirm-boundary-scene-${block.ordinal}`}
              ref={(el) => {
                sceneRefs.current[block.ordinal] = el;
              }}
            >
              <h2>场景{block.ordinal}</h2>
              {block.paragraphs.map((p) => (
                <p key={p.id}>{p.raw_text}</p>
              ))}
            </article>
          </div>
        ))}
      </div>

      {error && (
        <p className="notice error" data-testid="confirm-boundary-error">
          {error}
        </p>
      )}

      <footer className="confirm-boundary-actions" data-testid="confirm-boundary-actions">
        <div className="confirm-boundary-actions-left">
          <button
            type="button"
            className="secondary"
            data-testid="confirm-boundary-cancel"
            disabled={cancelMutation.isPending || confirmMutation.isPending}
            onClick={() => cancelMutation.mutate()}
          >
            取消本次分析
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="confirm-boundary-reidentify"
            disabled={confirmMutation.isPending}
            onClick={() => {
              if (
                window.confirm(
                  "重新识别场景边界可能产生新的模型费用。确认继续？",
                )
              ) {
                onReidentify?.();
              }
            }}
          >
            重新识别
          </button>
        </div>
        <button
          type="button"
          className="primary"
          data-testid="confirm-boundary-submit"
          disabled={
            confirmMutation.isPending ||
            proposal?.validation_status !== "valid" ||
            !proposal?.proposal_fingerprint
          }
          onClick={handleConfirm}
        >
          {confirmMutation.isPending ? "正在确认…" : "确认边界并继续"}
        </button>
      </footer>

      <details className="confirm-boundary-tech" data-testid="confirm-boundary-tech">
        <summary>技术详情</summary>
        <dl>
          <div>
            <dt>Review ID</dt>
            <dd>#{reviewId}</dd>
          </div>
          <div>
            <dt>Run ID</dt>
            <dd>#{reviewQuery.data?.analysis_run_id}</dd>
          </div>
          <div>
            <dt>方案指纹</dt>
            <dd>{proposal?.proposal_fingerprint}</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
