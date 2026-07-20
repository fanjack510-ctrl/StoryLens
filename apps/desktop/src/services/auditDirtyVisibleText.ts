/** Patterns that must never appear in user-visible audit UI text. */
export const AUDIT_DIRTY_VISIBLE_PATTERNS: RegExp[] = [
  /undefined/i,
  /Sundefined/i,
  /\bnull\b/i,
  /\bNaN\b/,
  /\[object Object\]/,
];

export function findDirtyVisibleToken(text: string): string | null {
  const value = text.trim();
  if (!value) return null;
  for (const re of AUDIT_DIRTY_VISIBLE_PATTERNS) {
    if (re.test(value)) return value;
  }
  return null;
}
