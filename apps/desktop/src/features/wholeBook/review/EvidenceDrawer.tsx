/**
 * Phase 1D Agent L — Evidence Drawer prototype (isolated).
 * Does not write to the database. Not registered in product navigation.
 */

import type { WholeBookEvidenceRefDto, EvidenceRole } from "../contracts/evidence";
import type { EvidenceIntegrityStatus } from "../contracts/keys";

export type EvidenceDrawerTheme = "light" | "dark";

export type WholeBookEvidenceDrawerProps = {
  open: boolean;
  title?: string;
  evidence: WholeBookEvidenceRefDto[];
  theme?: EvidenceDrawerTheme;
  onClose: () => void;
  onOpenDeepLink?: (ref: WholeBookEvidenceRefDto) => void;
  className?: string;
};

const ROLE_LABEL: Record<EvidenceRole, string> = {
  support: "支持",
  contradict: "反证",
  context: "上下文",
};

const INTEGRITY_LABEL: Record<EvidenceIntegrityStatus, string> = {
  valid: "有效",
  stale: "过期",
  hash_mismatch: "哈希不匹配",
  missing: "缺失",
  inaccessible: "不可访问",
};

export function EvidenceRoleBadge({ role }: { role: EvidenceRole }) {
  return (
    <span
      className={`sl-ev-role sl-ev-role--${role}`}
      data-testid="evidence-role-badge"
    >
      {ROLE_LABEL[role] ?? role}
    </span>
  );
}

export function EvidenceIntegrityBadge({
  status,
}: {
  status: EvidenceIntegrityStatus;
}) {
  return (
    <span
      className={`sl-ev-integrity sl-ev-integrity--${status}`}
      data-testid="evidence-integrity-badge"
      title={status}
    >
      {INTEGRITY_LABEL[status] ?? status}
    </span>
  );
}

export function EvidenceSourceLink({
  evidence,
  onOpen,
}: {
  evidence: WholeBookEvidenceRefDto;
  onOpen?: (ref: WholeBookEvidenceRefDto) => void;
}) {
  const blocked =
    evidence.integrity_status === "hash_mismatch" ||
    evidence.integrity_status === "missing" ||
    evidence.integrity_status === "inaccessible";
  return (
    <button
      type="button"
      className="sl-ev-source-link"
      data-testid="evidence-source-link"
      disabled={blocked && evidence.integrity_status !== "hash_mismatch"}
      aria-disabled={blocked}
      onClick={() => {
        if (evidence.integrity_status === "hash_mismatch") {
          // Explicit warning path — caller must not silent-locate.
          onOpen?.(evidence);
          return;
        }
        if (!blocked) onOpen?.(evidence);
      }}
    >
      原文深链
      {evidence.integrity_status === "hash_mismatch" ? "（需确认哈希警告）" : ""}
    </button>
  );
}

export function EvidencePreviewCard({
  item,
  onOpenDeepLink,
}: {
  item: WholeBookEvidenceRefDto;
  onOpenDeepLink?: (ref: WholeBookEvidenceRefDto) => void;
}) {
  return (
    <article
      className="sl-ev-preview-card"
      data-testid="evidence-preview-card"
      tabIndex={0}
    >
      <header className="sl-ev-preview-card__header">
        <EvidenceRoleBadge role={item.evidence_role} />
        <EvidenceIntegrityBadge status={item.integrity_status} />
      </header>
      <h4 className="sl-ev-preview-card__chapter">{item.chapter_title || "（无章节标题）"}</h4>
      <p className="sl-ev-preview-card__preview">
        {item.paragraph_preview ||
          (item.integrity_status === "missing"
            ? "原文缺失，无法预览"
            : "（无预览）")}
      </p>
      <dl className="sl-ev-preview-card__meta">
        <div>
          <dt>Snapshot</dt>
          <dd>{item.book_snapshot_id}</dd>
        </div>
        <div>
          <dt>Hash</dt>
          <dd className="sl-ev-mono">{item.paragraph_content_hash.slice(0, 12)}…</dd>
        </div>
        <div>
          <dt>类型</dt>
          <dd>{item.evidence_type}</dd>
        </div>
      </dl>
      {item.integrity_status === "hash_mismatch" ? (
        <p className="sl-ev-warn" role="alert">
          段落哈希不匹配：禁止静默跳转定位。请核对 Snapshot 后再打开原文。
        </p>
      ) : null}
      {item.integrity_status === "missing" ? (
        <p className="sl-ev-warn" role="status">
          Evidence 目标缺失，界面保持可用。
        </p>
      ) : null}
      <EvidenceSourceLink evidence={item} onOpen={onOpenDeepLink} />
    </article>
  );
}

export function WholeBookEvidenceDrawer({
  open,
  title = "Evidence",
  evidence,
  theme = "light",
  onClose,
  onOpenDeepLink,
  className,
}: WholeBookEvidenceDrawerProps) {
  if (!open) return null;
  return (
    <aside
      className={`sl-ev-drawer sl-ev-drawer--${theme} ${className ?? ""}`.trim()}
      data-testid="whole-book-evidence-drawer"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <header className="sl-ev-drawer__header">
        <h3>{title}</h3>
        <button type="button" aria-label="关闭 Evidence Drawer" onClick={onClose}>
          关闭
        </button>
      </header>
      <div className="sl-ev-drawer__body">
        {evidence.length === 0 ? (
          <p data-testid="evidence-empty">暂无 Evidence</p>
        ) : (
          evidence.map((item) => (
            <EvidencePreviewCard
              key={`${item.evidence_type}-${item.evidence_id}`}
              item={item}
              onOpenDeepLink={onOpenDeepLink}
            />
          ))
        )}
      </div>
      <p className="sl-ev-drawer__note">只读原型 — 不在 Drawer 内编辑数据库</p>
    </aside>
  );
}
