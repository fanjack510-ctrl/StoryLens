/** Mock Run error codes — must match backend MockRunErrorCode. */

export const MOCK_RUN_ERROR_CODES = [
  "MOCK_LAB_DISABLED",
  "MOCK_LAB_ENVIRONMENT_NOT_ALLOWED",
  "MOCK_LAB_LOOPBACK_REQUIRED",
  "MOCK_LAB_REQUEST_MARKER_REQUIRED",
  "MOCK_LAB_ENGINE_REQUIRED",
  "MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE",
  "MOCK_ENGINE_REQUIRED",
  "MOCK_RUN_NOT_FOUND",
  "MOCK_RUN_ALREADY_ACTIVE",
  "MOCK_RUN_STATE_CONFLICT",
  "MOCK_RUN_OPERATION_NOT_ALLOWED",
  "MOCK_RUN_IDEMPOTENCY_CONFLICT",
  "MOCK_RUN_SNAPSHOT_INVALID",
  "MOCK_RUN_CHECKPOINT_INVALID",
  "MOCK_RUN_ENGINE_VERSION_MISMATCH",
  "MOCK_RUN_BUDGET_EXCEEDED",
  "MOCK_RUN_CANCELLED",
  "MOCK_RUN_NOT_RECOVERABLE",
  "MOCK_RUN_NON_MOCK_TARGET",
] as const;

export type MockRunErrorCode = (typeof MOCK_RUN_ERROR_CODES)[number];

export const MOCK_RUN_ERROR_MESSAGES: Record<MockRunErrorCode, string> = {
  MOCK_LAB_DISABLED: "Mock Lab is disabled. Set WHOLE_BOOK_MOCK_LAB_ENABLED only in development/test.",
  MOCK_LAB_ENVIRONMENT_NOT_ALLOWED: "Mock Lab is not allowed in this application environment.",
  MOCK_LAB_LOOPBACK_REQUIRED: "Mock Lab write requests must originate from loopback.",
  MOCK_LAB_REQUEST_MARKER_REQUIRED: "Mock Lab request marker is required.",
  MOCK_LAB_ENGINE_REQUIRED: "Mock Lab requires MockWholeBookAnalysisEngine.",
  MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE: "Requested engine is not marked non_production.",
  MOCK_ENGINE_REQUIRED: "A mock whole-book engine is required for this operation.",
  MOCK_RUN_NOT_FOUND: "Mock run was not found.",
  MOCK_RUN_ALREADY_ACTIVE: "An active mock run already exists for this book.",
  MOCK_RUN_STATE_CONFLICT: "Run state conflict; expected_state/version did not match.",
  MOCK_RUN_OPERATION_NOT_ALLOWED: "Operation is not allowed for the current run state.",
  MOCK_RUN_IDEMPOTENCY_CONFLICT: "Idempotency key conflicts with a different request payload.",
  MOCK_RUN_SNAPSHOT_INVALID: "Book snapshot is missing, mismatched, or not completed.",
  MOCK_RUN_CHECKPOINT_INVALID: "Checkpoint is missing or schema/version incompatible.",
  MOCK_RUN_ENGINE_VERSION_MISMATCH: "Engine id/version does not match the run record.",
  MOCK_RUN_BUDGET_EXCEEDED: "Mock synthetic budget exceeded; no assets were written.",
  MOCK_RUN_CANCELLED: "Mock run was cancelled.",
  MOCK_RUN_NOT_RECOVERABLE: "Mock run cannot be recovered.",
  MOCK_RUN_NON_MOCK_TARGET: "Target run is not a mock lab run.",
};
