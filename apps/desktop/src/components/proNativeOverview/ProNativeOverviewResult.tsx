import { Link } from "react-router-dom";
import { firstEvidenceHref } from "../../services/proNativeOverviewDeepLink";
import type {
  CoverageDTO,
  OverviewApiResponse,
  OverviewField,
} from "../../services/proNativeOverviewApi";
import {
  resolveEnginePresentation,
  WALKING_SKELETON_USER_NOTICE,
  type EnginePresentation,
} from "../../services/proNativeOverviewFlag";
import { fieldStatusLabel } from "../../services/proNativeOverviewStages";

const RESULT_FIELDS: Array<{ key: keyof ResultFieldMap; label: string }> = [
  { key: "protagonist", label: "主角" },
  { key: "protagonist_core_goal", label: "主角核心目标" },
  { key: "primary_conflict", label: "全书主要矛盾" },
  { key: "central_question", label: "核心悬念或核心问题" },
  { key: "key_turning_points", label: "关键转折" },
  { key: "ending_state", label: "结局状态" },
  { key: "logline", label: "一句话故事" },
  { key: "synopsis", label: "全书概要" },
];

type ResultFieldMap = {
  protagonist?: OverviewField | null;
  protagonist_core_goal?: OverviewField | null;
  primary_conflict?: OverviewField | null;
  central_question?: OverviewField | null;
  key_turning_points?: OverviewField | null;
  ending_state?: OverviewField | null;
  logline?: OverviewField | null;
  synopsis?: OverviewField | null;
};

function formatFieldValue(value: unknown): string {
  if (value == null || value === "") return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isInsufficient(field: OverviewField | null | undefined): boolean {
  if (!field) return true;
  if (field.status === "insufficient_evidence") return true;
  const text = formatFieldValue(field.value).trim();
  return !text;
}

function EngineBadge({ engine }: { engine: EnginePresentation }) {
  return (
    <span
      data-testid="pro-native-overview-engine-badge"
      data-engine-kind={engine.kind}
    >
      {engine.label}
      {engine.engineId ? `（${engine.engineId}）` : ""}
    </span>
  );
}

function OverviewFieldCard({
  bookId,
  label,
  fieldKey,
  field,
  evidenceIndex,
}: {
  bookId: number;
  label: string;
  fieldKey: string;
  field: OverviewField | null | undefined;
  evidenceIndex: Parameters<typeof firstEvidenceHref>[2];
}) {
  const status = field?.status || "missing";
  const insufficient = isInsufficient(field);
  const href = firstEvidenceHref(bookId, field?.evidence_refs, evidenceIndex);
  const confidence =
    typeof field?.confidence === "number" ? field.confidence.toFixed(2) : "—";

  return (
    <article
      className="pro-native-overview-field"
      data-testid={`pro-native-overview-field-${fieldKey}`}
      data-status={status}
    >
      <header>
        <h3>{label}</h3>
        <p className="muted">
          状态：
          <span data-testid={`pro-native-overview-field-${fieldKey}-status`}>
            {fieldStatusLabel(field?.status)}
          </span>
          {" · "}
          置信度：{confidence}
        </p>
      </header>
      {insufficient ? (
        <p data-testid={`pro-native-overview-field-${fieldKey}-insufficient`}>
          暂未能可靠判断
        </p>
      ) : (
        <p data-testid={`pro-native-overview-field-${fieldKey}-value`}>
          {formatFieldValue(field?.value)}
        </p>
      )}
      {status === "conflicted" ? (
        <p className="notice" data-testid={`pro-native-overview-field-${fieldKey}-conflicted`}>
          证据存在冲突，请核对原文后再采信。
        </p>
      ) : null}
      {status === "low_confidence" && !insufficient ? (
        <p className="muted" data-testid={`pro-native-overview-field-${fieldKey}-low-confidence`}>
          置信度较低，建议结合 Evidence 核对。
        </p>
      ) : null}
      {href ? (
        <Link
          className="secondary"
          to={href}
          data-testid={`pro-native-overview-evidence-${fieldKey}`}
        >
          Evidence
        </Link>
      ) : (
        <button
          type="button"
          className="secondary"
          disabled
          data-testid={`pro-native-overview-evidence-${fieldKey}-missing`}
          title="缺少可跳转证据"
        >
          Evidence
        </button>
      )}
    </article>
  );
}

function CoveragePanel({ coverage }: { coverage: CoverageDTO }) {
  return (
    <section data-testid="pro-native-overview-coverage" className="pro-native-overview-coverage">
      <h3>原文覆盖（原生整书）</h3>
      <p className="muted" data-testid="pro-native-overview-coverage-note">
        此面板仅用于「Pro 原生全书概览」，不是「章节聚合洞察」的章节覆盖率。
      </p>
      <ul>
        <li data-testid="pro-native-overview-coverage-paragraphs">
          段落覆盖：{coverage.original_paragraphs_covered} /{" "}
          {coverage.original_paragraphs_total}（{coverage.original_coverage_percent}%）
        </li>
        <li data-testid="pro-native-overview-coverage-windows">
          窗口：{coverage.windows_completed} / {coverage.windows_total}
        </li>
        <li data-testid="pro-native-overview-coverage-evidence">
          Evidence 条数：{coverage.evidence_count ?? 0}
        </li>
      </ul>
    </section>
  );
}

type Props = {
  bookId: number;
  data: OverviewApiResponse;
};

/** Evidence-backed overview fields + native-only coverage panel (STEP 2.3-C3). */
export function ProNativeOverviewResult({ bookId, data }: Props) {
  const engine = resolveEnginePresentation(data.engine_id);
  return (
    <section data-testid="pro-native-overview-result">
      <h2>概览结果</h2>
      <p className="muted" data-testid="pro-native-overview-result-engine">
        Engine：
        <EngineBadge engine={engine} /> · version {data.engine_version || "—"}
        {engine.isFixture || !data.engine_id ? <> · {WALKING_SKELETON_USER_NOTICE}</> : null}
      </p>
      {data.coverage ? <CoveragePanel coverage={data.coverage} /> : null}
      {RESULT_FIELDS.map(({ key, label }) => (
        <OverviewFieldCard
          key={key}
          bookId={bookId}
          label={label}
          fieldKey={key}
          field={data.overview?.[key]}
          evidenceIndex={data.evidence_index}
        />
      ))}
    </section>
  );
}
