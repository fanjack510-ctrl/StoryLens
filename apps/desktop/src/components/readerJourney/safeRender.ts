import type {
  CharacterEffectItem,
  HookItem,
  InformationChangeItem,
  PayoffItem,
  ReaderQuestionItem,
  RiskPointItem,
  TechniqueItem,
  WritingTakeaway,
} from "../../types/readerJourneyProfileItems";

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isWritingTakeaway(value: unknown): value is WritingTakeaway {
  if (isNonEmptyString(value)) {
    return false;
  }
  return isPlainObject(value) && isNonEmptyString(value.summary);
}

export function normalizeWritingTakeaway(value: unknown): WritingTakeaway | null {
  if (isNonEmptyString(value)) {
    return { summary: value.trim() };
  }
  if (isWritingTakeaway(value)) {
    return {
      summary: value.summary.trim(),
      applicable_when: isNonEmptyString(value.applicable_when)
        ? value.applicable_when.trim()
        : undefined,
      avoid_when: isNonEmptyString(value.avoid_when) ? value.avoid_when.trim() : undefined,
    };
  }
  return null;
}

export function normalizeTechnique(value: unknown): TechniqueItem | null {
  if (!isPlainObject(value)) return null;
  const name = isNonEmptyString(value.name)
    ? value.name.trim()
    : isNonEmptyString(value.summary)
      ? value.summary.trim()
      : "";
  if (!name) return null;
  return {
    code: isNonEmptyString(value.code) ? value.code : undefined,
    name,
    mechanism: isNonEmptyString(value.mechanism) ? value.mechanism : undefined,
    reader_effect: isNonEmptyString(value.reader_effect) ? value.reader_effect : undefined,
    transfer_formula: isNonEmptyString(value.transfer_formula) ? value.transfer_formula : undefined,
    risk: isNonEmptyString(value.risk) ? value.risk : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

export function normalizeRiskPoint(value: unknown): RiskPointItem | null {
  if (!isPlainObject(value) || !isNonEmptyString(value.summary)) return null;
  return {
    type: isNonEmptyString(value.type) ? value.type : undefined,
    summary: value.summary.trim(),
    severity: typeof value.severity === "number" ? value.severity : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

export function normalizePayoff(value: unknown): PayoffItem | null {
  if (!isPlainObject(value) || !isNonEmptyString(value.summary)) return null;
  return {
    type: isNonEmptyString(value.type) ? value.type : undefined,
    summary: value.summary.trim(),
    strength: typeof value.strength === "number" ? value.strength : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

export function normalizeHook(value: unknown): HookItem | null {
  if (!isPlainObject(value) || !isNonEmptyString(value.summary)) return null;
  return {
    type: isNonEmptyString(value.type) ? value.type : undefined,
    summary: value.summary.trim(),
    strength: typeof value.strength === "number" ? value.strength : undefined,
    known: isNonEmptyString(value.known) ? value.known : undefined,
    gap: isNonEmptyString(value.gap) ? value.gap : undefined,
    continue_drive: isNonEmptyString(value.continue_drive) ? value.continue_drive : undefined,
    next_handoff: isNonEmptyString(value.next_handoff) ? value.next_handoff : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

export function normalizeReaderQuestion(value: unknown): ReaderQuestionItem | null {
  if (!isPlainObject(value)) return null;
  const question = isNonEmptyString(value.question) ? value.question.trim() : undefined;
  const answerSummary = isNonEmptyString(value.answer_summary)
    ? value.answer_summary.trim()
    : undefined;
  if (!question && !answerSummary) return null;
  return {
    question,
    source: isNonEmptyString(value.source) ? value.source : undefined,
    origin: isNonEmptyString(value.origin) ? value.origin : undefined,
    strength: typeof value.strength === "number" ? value.strength : undefined,
    answer_summary: answerSummary,
    answer_degree: isNonEmptyString(value.answer_degree) ? value.answer_degree : undefined,
    trigger_summary: isNonEmptyString(value.trigger_summary) ? value.trigger_summary : undefined,
    confidence: typeof value.confidence === "number" ? value.confidence : undefined,
    hook_type: isNonEmptyString(value.hook_type) ? value.hook_type : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

export function normalizeInformationChange(value: unknown): InformationChangeItem | null {
  if (!isPlainObject(value) || !isNonEmptyString(value.summary)) return null;
  return {
    type: isNonEmptyString(value.type) ? value.type : undefined,
    summary: value.summary.trim(),
    certainty: isNonEmptyString(value.certainty) ? value.certainty : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

export function normalizeCharacterEffect(value: unknown): CharacterEffectItem | null {
  if (!isPlainObject(value)) return null;
  const characterName = isNonEmptyString(value.character_name)
    ? value.character_name
    : isNonEmptyString(value.character)
      ? value.character
      : undefined;
  const trait = isNonEmptyString(value.trait_or_change)
    ? value.trait_or_change
    : isNonEmptyString(value.effect)
      ? value.effect
      : undefined;
  if (!characterName && !trait) return null;
  return {
    character_name: characterName,
    trait_or_change: trait,
    method: isNonEmptyString(value.method) ? value.method : undefined,
    evidence_paragraph_ids: asArray<string>(value.evidence_paragraph_ids).filter(isNonEmptyString),
  };
}

/** Never pass unknown objects to React children. */
export function renderFallbackValue(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (import.meta.env.DEV) {
    console.warn("[reader-journey] unsupported detail value", value);
  }
  return "该分析项结构暂不支持";
}
