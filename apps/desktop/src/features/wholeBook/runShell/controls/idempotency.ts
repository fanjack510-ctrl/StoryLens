/** Stable operation / create idempotency keys for Mock Lab. */

export function createOperationIdempotencyKey(
  action: string,
  runId: number,
  extra = "",
): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `mock-op:${action}:${runId}:${extra}:${rand}`;
}

/**
 * User-confirm-stable create key.
 * Same inputs → same key until the user regenerates (new confirmEpoch).
 */
export function createMockRunIdempotencyKey(params: {
  bookId: number;
  snapshotId: number;
  analysisMode: string;
  modulesFingerprint: string;
  configurationFingerprint: string;
  mockProfile: string;
  confirmEpoch: number;
}): string {
  return [
    "mock-create",
    params.bookId,
    params.snapshotId,
    params.analysisMode,
    params.modulesFingerprint,
    params.configurationFingerprint,
    params.mockProfile,
    params.confirmEpoch,
  ].join(":");
}

export function fingerprintModules(modules: readonly string[]): string {
  return [...modules].sort().join(",");
}
