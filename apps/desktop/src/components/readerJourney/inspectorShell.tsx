/**
 * Pure presentation shell for Context Inspector.
 * No business state, no selection semantics, no analysis generation.
 */
import { type ReactNode, useState } from "react";

export type InspectorEmptyKind =
  | "no-question-chain"
  | "no-hook-payoff"
  | "no-technique"
  | "no-evidence"
  | "no-risk"
  | "no-related-scenes"
  | "no-lifecycle"
  | "no-selection"
  | "no-section";

const EMPTY_COPY: Record<
  InspectorEmptyKind,
  { title: string; description: string }
> = {
  "no-question-chain": {
    title: "未识别出明确问题链",
    description:
      "当前分析结果中没有独立的问题建立、延续或回答记录。它可能主要承担情绪推进、动作推进或信息确认。",
  },
  "no-hook-payoff": {
    title: "未识别出明确的钩子或回报",
    description:
      "这不代表场景无作用，可能由其他结构功能承担推进。",
  },
  "no-technique": {
    title: "未提取出可复用技法",
    description: "当前分析未提取出可复用的明确写作技法。",
  },
  "no-evidence": {
    title: "暂无可用证据",
    description: "当前对象没有可定位的段落证据记录。",
  },
  "no-risk": {
    title: "未识别出明确流失风险",
    description: "当前阶段未识别出明确的结构性流失风险。",
  },
  "no-related-scenes": {
    title: "暂无相关场景",
    description: "当前阶段范围内没有可展示的场景节点。",
  },
  "no-lifecycle": {
    title: "生命周期链不完整",
    description: "当前问题尚未形成可展示的完整生命周期链。",
  },
  "no-selection": {
    title: "尚未选择分析对象",
    description: "选择一个阶段、场景或曲线节点，查看详细分析。",
  },
  "no-section": {
    title: "本小节暂无内容",
    description: "当前分析结果中没有可展示的对应记录。",
  },
};

type ShellProps = {
  children: ReactNode;
  testId: string;
  className?: string;
};

export function JourneyInspectorShell({ children, testId, className }: ShellProps) {
  return (
    <aside
      className={`journey-detail-drawer journey-inspector-shell ${className ?? ""}`}
      data-testid={testId}
      data-inspector-shell="true"
    >
      {children}
    </aside>
  );
}

type HeaderProps = {
  title: string;
  meta: string;
  pills?: string[];
  onClose?: () => void;
  locateLabel?: string;
  onLocate?: () => void;
  titleTestId?: string;
};

export function JourneyInspectorHeader({
  title,
  meta,
  pills = [],
  onClose,
  locateLabel,
  onLocate,
  titleTestId,
}: HeaderProps) {
  const visiblePills = pills.filter(Boolean).slice(0, 2);
  return (
    <header className="journey-inspector-header" data-testid="journey-inspector-header">
      <div className="journey-inspector-header-main">
        <h3 data-testid={titleTestId ?? "journey-inspector-title"}>{title}</h3>
        <p className="journey-inspector-meta" data-testid="journey-inspector-meta">
          {meta}
          {visiblePills.map((pill) => (
            <span key={pill} className="journey-inspector-pill" data-testid="journey-inspector-pill">
              {pill}
            </span>
          ))}
        </p>
      </div>
      <div className="journey-inspector-header-actions">
        {onLocate && locateLabel ? (
          <button type="button" className="journey-inline-button" onClick={onLocate}>
            {locateLabel}
          </button>
        ) : null}
        {onClose ? (
          <button type="button" data-testid="journey-inspector-close" onClick={onClose}>
            关闭
          </button>
        ) : null}
      </div>
    </header>
  );
}

export function JourneyPrimaryConclusion({
  text,
  testId = "journey-primary-conclusion",
}: {
  text: string;
  testId?: string;
}) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return (
    <p className="journey-primary-conclusion" data-testid={testId}>
      {trimmed}
    </p>
  );
}

export function JourneyInspectorSection({
  title,
  children,
  testId,
}: {
  title: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <section className="journey-inspector-section" data-testid={testId}>
      <h4 className="journey-inspector-section-title">{title}</h4>
      <div className="journey-inspector-section-body">{children}</div>
    </section>
  );
}

export function JourneyInspectorEmptyState({
  kind,
  testId,
  actionLabel,
  onAction,
}: {
  kind: InspectorEmptyKind;
  testId: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const copy = EMPTY_COPY[kind];
  return (
    <div
      className="journey-inspector-empty-state"
      data-testid={testId}
      data-empty-kind={kind}
    >
      <strong>{copy.title}</strong>
      <p>{copy.description}</p>
      {actionLabel && onAction ? (
        <button type="button" className="journey-inline-button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function JourneyCompactMetrics({
  items,
  testId = "journey-compact-metrics",
}: {
  items: Array<{ key: string; label: string; value: number; title?: string }>;
  testId?: string;
}) {
  if (!items.length) return null;
  return (
    <div className="journey-compact-metrics" data-testid={testId}>
      {items.map((item, index) => (
        <span
          key={item.key}
          className="journey-compact-metric"
          data-testid={`score-bar-${item.key}`}
          title={item.title}
        >
          {index > 0 ? <span className="journey-compact-metric-sep" aria-hidden>
            ｜
          </span> : null}
          {item.label} {Math.round(item.value)}
        </span>
      ))}
    </div>
  );
}

export type EvidenceRow = {
  paragraphId: string;
  conclusion: string;
  kind: string;
};

const EVIDENCE_DEFAULT_LIMIT = 5;

export function JourneyEvidenceList({
  rows,
  onLocateEvidence,
  testId = "journey-evidence-list",
}: {
  rows: EvidenceRow[];
  onLocateEvidence: (paragraphId: string) => void;
  testId?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!rows.length) {
    return <JourneyInspectorEmptyState kind="no-evidence" testId="empty-evidence" />;
  }
  const visible = expanded ? rows : rows.slice(0, EVIDENCE_DEFAULT_LIMIT);
  const hidden = rows.length - EVIDENCE_DEFAULT_LIMIT;
  return (
    <div className="journey-evidence-compact" data-testid={testId}>
      <ul className="scene-detail-evidence-list journey-evidence-compact-list">
        {visible.map((row) => (
          <li key={`${row.paragraphId}-${row.kind}-${row.conclusion}`}>
            <div>
              <code>{row.paragraphId}</code>
              <small>
                {row.kind} · {row.conclusion}
              </small>
            </div>
            <button
              type="button"
              data-testid={`journey-evidence-${row.paragraphId}`}
              onClick={() => onLocateEvidence(row.paragraphId)}
            >
              定位正文
            </button>
          </li>
        ))}
      </ul>
      {!expanded && hidden > 0 ? (
        <button
          type="button"
          className="journey-inline-button"
          data-testid="journey-evidence-expand"
          onClick={() => setExpanded(true)}
        >
          展开全部 {rows.length} 条
        </button>
      ) : null}
      {expanded && rows.length > EVIDENCE_DEFAULT_LIMIT ? (
        <button
          type="button"
          className="journey-inline-button"
          data-testid="journey-evidence-collapse"
          onClick={() => setExpanded(false)}
        >
          收起
        </button>
      ) : null}
    </div>
  );
}

export function JourneyRelatedObjectList({
  items,
  testId,
}: {
  items: Array<{
    key: string;
    primary: string;
    secondary?: string;
    meta?: string;
    onClick?: () => void;
    testId?: string;
  }>;
  testId?: string;
}) {
  if (!items.length) {
    return (
      <JourneyInspectorEmptyState kind="no-related-scenes" testId="empty-related-scenes" />
    );
  }
  return (
    <ul className="journey-related-compact" data-testid={testId}>
      {items.map((item) => (
        <li key={item.key}>
          {item.onClick ? (
            <button
              type="button"
              className="journey-related-row"
              data-testid={item.testId}
              onClick={item.onClick}
            >
              <span>{item.primary}</span>
              {item.secondary ? <small>{item.secondary}</small> : null}
              {item.meta ? <b>{item.meta}</b> : null}
            </button>
          ) : (
            <div className="journey-related-row journey-related-row-static" data-testid={item.testId}>
              <span>{item.primary}</span>
              {item.secondary ? <small>{item.secondary}</small> : null}
              {item.meta ? <b>{item.meta}</b> : null}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function JourneyInspectorBody({
  children,
  testId = "journey-inspector-body",
}: {
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div className="journey-inspector-body" data-testid={testId} data-scroll-region="inspector">
      {children}
    </div>
  );
}

export function JourneyInspectorTabs({
  tabs,
  active,
  onChange,
  testId,
}: {
  tabs: Array<{ id: string; label: string; testId: string }>;
  active: string;
  onChange: (id: string) => void;
  testId: string;
}) {
  return (
    <div className="scene-detail-tabs journey-inspector-tabs" data-testid={testId} role="tablist">
      {tabs.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          data-testid={item.testId}
          className={active === item.id ? "active" : ""}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
