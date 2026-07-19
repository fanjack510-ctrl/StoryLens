/** Frontend types aligned with backend Scene Reader Journey contract v1.3. */

export type WritingTakeaway = {
  summary: string;
  applicable_when?: string;
  avoid_when?: string;
};

export type TechniqueItem = {
  code?: string;
  name: string;
  mechanism?: string;
  reader_effect?: string;
  transfer_formula?: string;
  risk?: string;
  evidence_paragraph_ids?: string[];
};

export type RiskPointItem = {
  type?: string;
  summary: string;
  severity?: number;
  evidence_paragraph_ids?: string[];
};

export type PayoffItem = {
  type?: string;
  summary: string;
  strength?: number;
  evidence_paragraph_ids?: string[];
};

export type HookItem = {
  type?: string;
  summary: string;
  strength?: number;
  known?: string;
  gap?: string;
  continue_drive?: string;
  next_handoff?: string;
  evidence_paragraph_ids?: string[];
};

export type ReaderQuestionItem = {
  question?: string;
  source?: string;
  origin?: string;
  strength?: number;
  answer_summary?: string;
  answer_degree?: string;
  trigger_summary?: string;
  confidence?: number;
  hook_type?: string;
  evidence_paragraph_ids?: string[];
};

export type InformationChangeItem = {
  type?: string;
  summary: string;
  certainty?: string;
  evidence_paragraph_ids?: string[];
};

export type CharacterEffectItem = {
  character_name?: string;
  /** Legacy alias used by older mocks. */
  character?: string;
  trait_or_change?: string;
  /** Legacy alias. */
  effect?: string;
  method?: string;
  evidence_paragraph_ids?: string[];
};
