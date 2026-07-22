import type { ReactNode } from "react";
import { lifecycleLabelZh, payoffTypeZh } from "./journeyUiLabels";
import type { WritingTakeaway } from "../../types/readerJourneyProfileItems";
import {
  asArray,
  isNonEmptyString,
  normalizeCharacterEffect,
  normalizeHook,
  normalizeInformationChange,
  normalizePayoff,
  normalizeReaderQuestion,
  normalizeRiskPoint,
  normalizeTechnique,
  normalizeWritingTakeaway,
  renderFallbackValue,
} from "./safeRender";

/** Normalize writing_takeaways across string | string[] | object | object[]. */
export function normalizeWritingTakeawayList(items: unknown): WritingTakeaway[] {
  if (items == null) return [];
  const list = Array.isArray(items) ? items : [items];
  return list
    .map((raw) => normalizeWritingTakeaway(raw))
    .filter((item): item is WritingTakeaway => item != null);
}

function EvidenceButtons({
  ids,
  onLocate,
}: {
  ids?: string[];
  onLocate?: (paragraphId: string) => void;
}) {
  const list = asArray<string>(ids).filter(isNonEmptyString);
  if (!list.length || !onLocate) return null;
  return (
    <div className="journey-field-evidence">
      {list.map((id) => (
        <button key={id} type="button" onClick={() => onLocate(id)}>
          {id}
        </button>
      ))}
    </div>
  );
}

function UnsupportedItem({ value }: { value: unknown }) {
  const text = renderFallbackValue(value);
  if (!text) return null;
  return <p className="journey-field-unsupported">{text}</p>;
}

export function WritingTakeawayList({ items }: { items: unknown }) {
  const normalized = normalizeWritingTakeawayList(items);
  const list = Array.isArray(items) ? items : items == null ? [] : [items];
  if (!list.length) {
    return <p className="journey-field-empty">暂无可迁移写作启示</p>;
  }

  return (
    <div className="journey-takeaway-list" data-testid="journey-writing-takeaways">
      {!normalized.length ? <p className="journey-field-empty">暂无可迁移写作启示</p> : null}
      {list.map((raw, index) => {
        const item = normalizeWritingTakeaway(raw);
        if (!item) {
          return <UnsupportedItem key={`takeaway-fallback-${index}`} value={raw} />;
        }
        return (
          <div key={`takeaway-${index}`} className="journey-takeaway" data-testid="journey-takeaway-item">
            <p className="journey-takeaway__summary">{item.summary}</p>
            {item.applicable_when ? (
              <p className="journey-takeaway__meta">
                <span>适用：</span>
                {item.applicable_when}
              </p>
            ) : null}
            {item.avoid_when ? (
              <p className="journey-takeaway__meta">
                <span>慎用：</span>
                {item.avoid_when}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function TechniqueList({
  items,
  onLocateEvidence,
}: {
  items: unknown;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return <p className="journey-field-empty">暂无技法记录</p>;
  return (
    <ul className="journey-field-list" data-testid="journey-techniques">
      {list.map((raw, index) => {
        const item = normalizeTechnique(raw);
        if (!item) {
          return (
            <li key={`tech-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`tech-${index}`} className="journey-technique">
            <b>{item.name}</b>
            {item.mechanism ? <p>机制：{item.mechanism}</p> : null}
            {item.reader_effect ? <p>读者效果：{item.reader_effect}</p> : null}
            {item.transfer_formula ? <p>迁移公式：{item.transfer_formula}</p> : null}
            {item.risk ? <p>流失风险：{item.risk}</p> : null}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function RiskPointList({
  items,
  onLocateEvidence,
}: {
  items: unknown;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return null;
  return (
    <ul className="journey-field-list" data-testid="journey-risk-points">
      {list.map((raw, index) => {
        const item = normalizeRiskPoint(raw);
        if (!item) {
          return (
            <li key={`risk-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`risk-${index}`}>
            {item.type ? `${item.type}：` : ""}
            {item.summary}
            {item.severity != null ? `（severity ${item.severity}）` : ""}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function PayoffList({
  items,
  onLocateEvidence,
}: {
  items: unknown;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return null;
  return (
    <ul className="journey-field-list" data-testid="journey-payoffs">
      {list.map((raw, index) => {
        const item = normalizePayoff(raw);
        if (!item) {
          return (
            <li key={`payoff-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`payoff-${index}`} className="journey-payoff-item">
            <b>{payoffTypeZh(item.type)}</b>
            <p>{item.summary}</p>
            {item.strength != null ? <small>强度 {item.strength}</small> : null}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function HookList({
  items,
  onLocateEvidence,
}: {
  items: unknown;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return null;
  return (
    <ul className="journey-field-list" data-testid="journey-hooks">
      {list.map((raw, index) => {
        const item = normalizeHook(raw);
        if (!item) {
          return (
            <li key={`hook-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`hook-${index}`} className="journey-hook-item">
            <b>
              {item.type ?? "hook"} · {item.summary}
              {item.strength != null ? `（${item.strength}）` : ""}
            </b>
            {item.known ? <p>已知：{item.known}</p> : null}
            {item.gap ? <p>缺口：{item.gap}</p> : null}
            {item.continue_drive && !/^(继续阅读|继续读下去|继续往下读|想继续读|继续读)$/.test(item.continue_drive.replace(/\s+/g, "")) ? (
              <p>续读动力：{item.continue_drive}</p>
            ) : null}
            {item.next_handoff ? <p>下场承接：{item.next_handoff}</p> : null}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function ReaderQuestionList({
  items,
  emptyLabel = "无",
  onLocateEvidence,
}: {
  items: unknown;
  emptyLabel?: string;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return <p className="journey-field-empty">{emptyLabel}</p>;
  return (
    <ul className="journey-field-list" data-testid="journey-reader-questions">
      {list.map((raw, index) => {
        const item = normalizeReaderQuestion(raw);
        if (!item) {
          return (
            <li key={`q-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`q-${index}`}>
            {item.question ? <p>{item.question}</p> : null}
            {item.trigger_summary ? <p>触发：{item.trigger_summary}</p> : null}
            {item.answer_summary ? (
              <p>
                回答：{item.answer_summary}
                {item.answer_degree ? `（${item.answer_degree}）` : ""}
              </p>
            ) : null}
            {item.source || item.origin ? (
              <p>
                状态：{lifecycleLabelZh(item.source ?? item.origin)}
                {item.strength != null ? ` · 强度 ${item.strength}` : ""}
              </p>
            ) : item.strength != null ? (
              <p>强度 {item.strength}</p>
            ) : null}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function InformationChangeList({
  items,
  onLocateEvidence,
}: {
  items: unknown;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return null;
  return (
    <ul className="journey-field-list" data-testid="journey-information-changes">
      {list.map((raw, index) => {
        const item = normalizeInformationChange(raw);
        if (!item) {
          return (
            <li key={`info-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`info-${index}`}>
            {item.type ? `${item.type}：` : ""}
            {item.summary}
            {item.certainty ? `（${item.certainty}）` : ""}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function CharacterEffectList({
  items,
  onLocateEvidence,
}: {
  items: unknown;
  onLocateEvidence?: (paragraphId: string) => void;
}) {
  const list = asArray(items);
  if (!list.length) return null;
  return (
    <ul className="journey-field-list" data-testid="journey-character-effects">
      {list.map((raw, index) => {
        const item = normalizeCharacterEffect(raw);
        if (!item) {
          return (
            <li key={`char-fallback-${index}`}>
              <UnsupportedItem value={raw} />
            </li>
          );
        }
        return (
          <li key={`char-${index}`}>
            <b>{item.character_name ?? "角色"}</b>
            {item.trait_or_change ? `：${item.trait_or_change}` : ""}
            {item.method ? `（${item.method}）` : ""}
            <EvidenceButtons ids={item.evidence_paragraph_ids} onLocate={onLocateEvidence} />
          </li>
        );
      })}
    </ul>
  );
}

export function DetailBlock({
  title,
  children,
  testId,
}: {
  title: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div className="journey-drawer-block" data-testid={testId}>
      <b>{title}</b>
      {children}
    </div>
  );
}
