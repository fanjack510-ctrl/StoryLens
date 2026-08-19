import { api } from "./apiClient";

/** Where a segment leaves the reader, relative to where it found them. */
export type EmotionDirection = "up" | "down" | "flat";

export type ShortFormSegment = {
  index: number;
  paragraph_start: number;
  paragraph_end: number;
  /** 分段字数 — counted by the engine, never asked of the model. */
  characters: number;
  phase: string;
  setting: string;
  beats: string[];
  craft: string;
  emotion_note: string;
  emotion_direction: EmotionDirection;
  /** What this segment reaches back to. Empty when it reaches back to nothing. */
  callback: string;
  evidence: string[];
};

export type ShortFormBeat = {
  beat: "起" | "承" | "转" | "合";
  segment_start: number;
  segment_end: number;
  title: string;
  summary: string;
};

/** A wording the engine found coming back, and where. Found by comparing the prose, not by
 *  asking — which is why it is a fact rather than a judgement. */
export type RecurringPhrase = { phrase: string; segments: number[] };

export type ShortFormResult = {
  version: string;
  availability: "available" | "partial" | "unavailable";
  title: string;
  character_count: number;
  one_line: string;
  genre: string;
  beats: ShortFormBeat[];
  segments: ShortFormSegment[];
  emotion_up: string[];
  emotion_down: string[];
  recurring: RecurringPhrase[];
};

/** A stored reading, with what it cost to make. */
export type ShortFormReading = {
  id: number;
  genre: string;
  provider_name: string;
  model_name: string;
  segments_planned: number;
  segments_resplit: number;
  provider_calls: number;
  created_at: string;
  result: ShortFormResult;
  reused?: boolean;
};

/** What the one segmentation call will cost. Segmentation sends the whole piece at once — a
 *  batched pass would invent scene breaks at its own batch edges — so the context window is a
 *  wall rather than a budget. Reported to warn, never to refuse. */
export type SegmentationEstimate = {
  paragraphs: number;
  characters: number;
  estimated_tokens: number;
  context_window: number;
  fits: boolean;
};

export type AnalysisForm = "short" | "long";

export type ShortFormPrepare = {
  book_id: number;
  book_title: string;
  chapter_count: number;
  character_count: number;
  is_short_form: boolean;
  /** What the reader chose. Empty string means they were never asked. */
  analysis_form: AnalysisForm | "";
  /** What the old length/chapter inference says — the default the panel offers. */
  suggested_form: AnalysisForm;
  segmentation: SegmentationEstimate;
  thresholds: { max_chars: number; soft_max_chars: number; max_chapters: number };
  genres: string[];
  latest: ShortFormReading | null;
};

export const shortFormApi = {
  prepare: (bookId: number) =>
    api<ShortFormPrepare>(`/api/v1/books/${bookId}/short-form/prepare`),

  /** Records whether this work is read as one piece or as a book. Changeable at any time:
   *  a value fixed at import with no way to correct it is wrong forever, which is exactly
   *  what happened to book titles. Nothing stored is recomputed or discarded. */
  setForm: (bookId: number, form: AnalysisForm) =>
    api<{ book_id: number; analysis_form: AnalysisForm; is_short_form: boolean }>(
      `/api/v1/books/${bookId}/analysis-form`,
      { method: "PUT", body: JSON.stringify({ form }) },
    ),

  /** Runs synchronously — a short piece is nine or ten provider calls, about a minute and a
   *  half. `force` is sent only from an explicit 重新分析, because the default must never be
   *  to pay for a second reading of the same book. */
  analyse: (bookId: number, body: { genre: string; force?: boolean; resegment?: boolean }) =>
    api<ShortFormReading>(`/api/v1/books/${bookId}/short-form/analyse`, {
      method: "POST",
      body: JSON.stringify({
        genre: body.genre,
        force: Boolean(body.force),
        resegment: Boolean(body.resegment),
      }),
    }),
};
