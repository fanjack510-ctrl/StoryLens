/** Compile-time client gates for whole-book Run UX (Phase 1D). */

/** Must remain false — production start stays disabled on the client. */
export const RUN_CREATE_ENABLED_IN_CLIENT = false;

export const WHOLE_BOOK_RUN_CREATE_PATH =
  "/api/v1/books/{book_id}/whole-book-runs";
export const WHOLE_BOOK_PREFLIGHT_PATH =
  "/api/v1/books/{book_id}/whole-book-runs/preflight";
