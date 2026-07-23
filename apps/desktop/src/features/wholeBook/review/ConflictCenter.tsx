/**
 * Phase 1D Agent L — Conflict Center prototype (isolated).
 * Blocking conflicts are never auto-resolved. Mutations via Review/Conflict service only.
 */

import { useMemo, useState } from "react";
import type { ConflictCenterItemDto } from "../contracts/conflictCenter";
import type { WholeBookEvidenceRefDto } from "../contracts/evidence";
import { BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN } from "../contracts/conflictCenter";
import { EvidencePreviewCard } from "./EvidenceDrawer";

export type ConflictCenterListProps = {
  items: ConflictCenterItemDto[];
  theme?: "light" | "dark";
  severityFilter?: string | "all";
  statusFilter?: string | "all";
  onSelect: (item: ConflictCenterItemDto) => void;
  className?: string;
};

export function ConflictCenterItem({
  item,
  selected,
  onSelect,
}: {
  item: ConflictCenterItemDto;
  selected?: boolean;
  onSelect: (item: ConflictCenterItemDto) => void;
}) {
  return (
    <button
      type="button"
      className={`sl-cf-item ${selected ? "is-selected" : ""}`}
      data-testid="conflict-center-item"
      aria-pressed={selected}
      onClick={() => onSelect(item)}
    >
      <span className={`sl-cf-sev sl-cf-sev--${item.severity}`}>{item.severity}</span>
      <span className={`sl-cf-status sl-cf-status--${item.status}`}>{item.status}</span>
      <strong>{item.conflict_type}</strong>
      <p>{item.description}</p>
      <small>
        modules: {item.affected_modules.join(", ") || "—"} · chapters:{" "}
        {item.affected_chapters.join(", ") || "—"}
      </small>
    </button>
  );
}

export function ConflictCenterList({
  items,
  theme = "light",
  severityFilter = "all",
  statusFilter = "all",
  onSelect,
  className,
}: ConflictCenterListProps) {
  const filtered = useMemo(() => {
    return items.filter((i) => {
      if (severityFilter !== "all" && i.severity !== severityFilter) return false;
      if (statusFilter !== "all" && i.status !== statusFilter) return false;
      return true;
    });
  }, [items, severityFilter, statusFilter]);

  return (
    <div
      className={`sl-cf-list sl-cf-list--${theme} ${className ?? ""}`.trim()}
      data-testid="conflict-center-list"
    >
      <p className="sl-cf-note">
        Blocking auto-resolve forbidden: {String(BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN)}
      </p>
      {filtered.map((item) => (
        <ConflictCenterItem key={String(item.conflict_id)} item={item} onSelect={onSelect} />
      ))}
      {filtered.length === 0 ? <p>无冲突</p> : null}
    </div>
  );
}

export function ConflictComparisonPanel({
  item,
}: {
  item: ConflictCenterItemDto;
}) {
  return (
    <div className="sl-cf-compare" data-testid="conflict-comparison-panel">
      <section>
        <h4>Left</h4>
        <p>
          {item.left_ref.ref_type}:{item.left_ref.ref_id}
        </p>
        <small>{item.left_ref.label}</small>
      </section>
      <section>
        <h4>Right</h4>
        <p>
          {item.right_ref.ref_type}:{item.right_ref.ref_id}
        </p>
        <small>{item.right_ref.label}</small>
      </section>
    </div>
  );
}

export function ConflictEvidenceComparison({
  evidence,
  onOpenDeepLink,
}: {
  evidence: WholeBookEvidenceRefDto[];
  onOpenDeepLink?: (ref: WholeBookEvidenceRefDto) => void;
}) {
  return (
    <div data-testid="conflict-evidence-comparison" className="sl-cf-evidence">
      <h4>Evidence 对比（预览，不含完整正文）</h4>
      {evidence.map((e) => (
        <EvidencePreviewCard
          key={`${e.evidence_type}-${e.evidence_id}`}
          item={e}
          onOpenDeepLink={onOpenDeepLink}
        />
      ))}
      {evidence.length === 0 ? <p>无 Evidence 引用</p> : null}
    </div>
  );
}

export type ConflictResolutionChoice =
  | "keep_old_canonical"
  | "confirm_new"
  | "create_corrected"
  | "dismiss"
  | "defer";

export function ConflictResolutionPanel({
  item,
  onResolve,
  onDismiss,
  onDefer,
  onCreateCorrected,
}: {
  item: ConflictCenterItemDto;
  onResolve: (choice: ConflictResolutionChoice) => void;
  onDismiss: () => void;
  onDefer: () => void;
  onCreateCorrected?: () => void;
}) {
  const [choice, setChoice] = useState<ConflictResolutionChoice>("keep_old_canonical");
  const closed = item.status === "resolved" || item.status === "dismissed";
  const blocking = item.severity === "blocking";

  return (
    <div
      className="sl-cf-resolution"
      data-testid="conflict-resolution-panel"
      aria-disabled={closed}
    >
      <h4>处理</h4>
      {closed ? (
        <p role="status">已终态：{item.status}</p>
      ) : (
        <>
          {blocking ? (
            <p className="sl-cf-warn" role="alert">
              Blocking 冲突不会被系统自动解决，必须显式人工处理。
            </p>
          ) : null}
          <label>
            方案
            <select
              value={choice}
              onChange={(e) => setChoice(e.target.value as ConflictResolutionChoice)}
              aria-label="冲突处理方案"
            >
              <option value="keep_old_canonical">保留旧 canonical</option>
              <option value="confirm_new">选择新版本</option>
              <option value="create_corrected">创建 corrected</option>
              <option value="dismiss">Dismiss</option>
              <option value="defer">延后处理</option>
            </select>
          </label>
          <p className="sl-cf-note">
            resolution schema/version 由后端 Review/Conflict Service 写入；前端不直接改
            ORM。
          </p>
          <div className="sl-rv-buttons">
            <button
              type="button"
              onClick={() => {
                if (choice === "dismiss") {
                  if (window.confirm("确认 dismiss？")) onDismiss();
                  return;
                }
                if (choice === "defer") {
                  onDefer();
                  return;
                }
                if (choice === "create_corrected") {
                  onCreateCorrected?.();
                  return;
                }
                if (window.confirm("确认提交冲突处理？")) onResolve(choice);
              }}
            >
              提交
            </button>
          </div>
        </>
      )}
      {item.resolution ? (
        <pre data-testid="conflict-resolution-json">
          {JSON.stringify(item.resolution, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

export function ConflictCenterPrototype({
  items,
  theme = "light",
}: {
  items: ConflictCenterItemDto[];
  theme?: "light" | "dark";
}) {
  const [selected, setSelected] = useState<ConflictCenterItemDto | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  return (
    <div
      className={`sl-cf-proto sl-cf-proto--${theme}`}
      data-testid="conflict-center-prototype"
    >
      <div className="sl-cf-filters">
        <label>
          severity
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            aria-label="按 severity 筛选"
          >
            <option value="all">all</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="blocking">blocking</option>
          </select>
        </label>
        <label>
          status
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="按 status 筛选"
          >
            <option value="all">all</option>
            <option value="open">open</option>
            <option value="resolved">resolved</option>
            <option value="dismissed">dismissed</option>
          </select>
        </label>
      </div>
      <ConflictCenterList
        items={items}
        theme={theme}
        severityFilter={severityFilter}
        statusFilter={statusFilter}
        onSelect={setSelected}
      />
      {selected ? (
        <>
          <ConflictComparisonPanel item={selected} />
          <ConflictEvidenceComparison evidence={selected.evidence_refs} />
          <ConflictResolutionPanel
            item={selected}
            onResolve={() => undefined}
            onDismiss={() => undefined}
            onDefer={() => undefined}
          />
        </>
      ) : null}
    </div>
  );
}
