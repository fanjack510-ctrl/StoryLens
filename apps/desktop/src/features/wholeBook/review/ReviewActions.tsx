/**
 * Phase 1D Agent L — Review Action UI prototype (isolated).
 * Mutations go through Review Action Adapter contract — never set is_canonical in UI.
 */

import { useMemo, useState } from "react";
import type { NarrativeReviewActionRequest } from "../contracts/review";
import type { NarrativeReviewAction } from "../contracts/keys";

export type ReviewUiStatus =
  | "candidate"
  | "confirmed"
  | "corrected"
  | "rejected";

export type NarrativeReviewActionsProps = {
  targetType: NarrativeReviewActionRequest["target_type"];
  targetId: string;
  expectedVersion: number | string;
  reviewStatus: ReviewUiStatus;
  isCanonical: boolean;
  isLocked: boolean;
  hasSupportEvidence: boolean;
  theme?: "light" | "dark";
  onSubmit: (request: NarrativeReviewActionRequest) => Promise<void> | void;
  onRefreshNeeded?: () => void;
  className?: string;
};

export function ReviewStatusBadge({
  status,
  isCanonical,
}: {
  status: ReviewUiStatus;
  isCanonical: boolean;
}) {
  return (
    <span
      className={`sl-rv-status sl-rv-status--${status}`}
      data-testid="review-status-badge"
    >
      {isCanonical ? "Canonical · " : "Candidate · "}
      {status}
    </span>
  );
}

export function LockStatusControl({
  isLocked,
  disabled,
  onLock,
  onUnlock,
}: {
  isLocked: boolean;
  disabled?: boolean;
  onLock: () => void;
  onUnlock: () => void;
}) {
  return (
    <div className="sl-rv-lock" data-testid="lock-status-control">
      <span>{isLocked ? "已锁定" : "未锁定"}</span>
      {isLocked ? (
        <button type="button" disabled={disabled} onClick={onUnlock}>
          解锁
        </button>
      ) : (
        <button type="button" disabled={disabled} onClick={onLock}>
          锁定
        </button>
      )}
    </div>
  );
}

export function VersionComparisonPanel({
  beforeTitle,
  afterTitle,
  beforeBody,
  afterBody,
}: {
  beforeTitle: string;
  afterTitle: string;
  beforeBody: string;
  afterBody: string;
}) {
  return (
    <div className="sl-rv-compare" data-testid="version-comparison-panel">
      <section>
        <h4>原版本</h4>
        <strong>{beforeTitle}</strong>
        <p>{beforeBody}</p>
      </section>
      <section>
        <h4>修改内容</h4>
        <strong>{afterTitle}</strong>
        <p>{afterBody}</p>
      </section>
    </div>
  );
}

export function CorrectVersionDialog({
  open,
  originalTitle,
  originalSummary,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  originalTitle: string;
  originalSummary: string;
  onCancel: () => void;
  onConfirm: (payload: { title: string; summary: string }) => void;
}) {
  const [title, setTitle] = useState(originalTitle);
  const [summary, setSummary] = useState(originalSummary);
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="纠正版本"
      data-testid="correct-version-dialog"
      className="sl-rv-correct-dialog"
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
      }}
    >
      <VersionComparisonPanel
        beforeTitle={originalTitle}
        afterTitle={title}
        beforeBody={originalSummary}
        afterBody={summary}
      />
      <label>
        新标题
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-label="纠正后标题"
        />
      </label>
      <label>
        新摘要
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          aria-label="纠正后摘要"
        />
      </label>
      <p className="sl-rv-note">将创建新 Version，不会覆盖原 Version。</p>
      <div className="sl-rv-actions">
        <button type="button" onClick={onCancel}>
          取消
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm("确认创建纠正版本？此操作不会覆盖原版本。")) {
              onConfirm({ title, summary });
            }
          }}
        >
          确认纠正
        </button>
      </div>
    </div>
  );
}

function buildRequest(
  action: NarrativeReviewAction,
  props: NarrativeReviewActionsProps,
  extras?: Partial<NarrativeReviewActionRequest>,
): NarrativeReviewActionRequest {
  return {
    action,
    target_type: props.targetType,
    target_id: props.targetId,
    expected_version: props.expectedVersion,
    actor: "user",
    correction_payload: {},
    evidence_changes: [],
    resolution_payload: {},
    reason: null,
    idempotency_key: `${action}-${props.targetId}-${Date.now()}`,
    ...extras,
  };
}

export function NarrativeReviewActions(props: NarrativeReviewActionsProps) {
  const [correctOpen, setCorrectOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmDisabled = !props.hasSupportEvidence;

  const statusLabel = useMemo(
    () => (
      <ReviewStatusBadge
        status={props.reviewStatus}
        isCanonical={props.isCanonical}
      />
    ),
    [props.reviewStatus, props.isCanonical],
  );

  const run = async (req: NarrativeReviewActionRequest) => {
    setError(null);
    try {
      await props.onSubmit(req);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("expected_version") || msg.includes("REVIEW_EXPECTED_VERSION")) {
        setError("并发冲突：expected_version 不匹配，请刷新后重试");
        props.onRefreshNeeded?.();
      } else {
        setError(msg);
      }
    }
  };

  return (
    <section
      className={`sl-rv-actions-panel sl-rv-actions-panel--${props.theme ?? "light"} ${props.className ?? ""}`.trim()}
      data-testid="narrative-review-actions"
    >
      {statusLabel}
      <LockStatusControl
        isLocked={props.isLocked}
        onLock={() => {
          if (window.confirm("确认锁定该 Asset/Relation？")) {
            void run(buildRequest("lock", props));
          }
        }}
        onUnlock={() => {
          if (window.confirm("确认显式解锁？")) {
            void run(buildRequest("unlock", props));
          }
        }}
      />
      <div className="sl-rv-buttons">
        <button
          type="button"
          disabled={confirmDisabled}
          title={confirmDisabled ? "无 Support Evidence，不可确认" : undefined}
          onClick={() => {
            if (window.confirm("确认将该版本标记为 confirmed？")) {
              void run(buildRequest("confirm", props));
            }
          }}
        >
          Confirm
        </button>
        <button type="button" onClick={() => setCorrectOpen(true)}>
          Correct
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm("确认拒绝该版本？不会物理删除。")) {
              void run(buildRequest("reject", props));
            }
          }}
        >
          Reject
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm("标记为 stale？")) {
              void run(buildRequest("mark_stale", props));
            }
          }}
        >
          Mark Stale
        </button>
      </div>
      <p className="sl-rv-note">不批量自动确认 · 前端不直接设置 is_canonical</p>
      {error ? (
        <p role="alert" data-testid="review-error">
          {error}
        </p>
      ) : null}
      <CorrectVersionDialog
        open={correctOpen}
        originalTitle="原标题"
        originalSummary="原摘要"
        onCancel={() => setCorrectOpen(false)}
        onConfirm={({ title, summary }) => {
          setCorrectOpen(false);
          void run(
            buildRequest("correct", props, {
              correction_payload: { title, summary },
            }),
          );
        }}
      />
    </section>
  );
}
