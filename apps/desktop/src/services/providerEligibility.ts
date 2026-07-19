import type { Provider } from "../types";

export type ProviderEligibility =
  | { status: "eligible"; blockers: string[] }
  | { status: "blocked"; blockers: string[] }
  | { status: "unknown"; blockers: string[] };

export const PROVIDER_ELIGIBILITY_MISSING =
  "Provider资格信息缺失，前后端版本可能不一致，请重启StoryLens。";

export function manualBoundaryEligibility(provider: Provider): ProviderEligibility {
  const value = (provider as unknown as Record<string, unknown>)
    .manual_boundary_candidate_eligible;
  const blockers = (provider as unknown as Record<string, unknown>)
    .manual_selection_blockers;
  if (value === true && Array.isArray(blockers)) return { status: "eligible", blockers };
  if (value === false && Array.isArray(blockers) && blockers.length > 0)
    return { status: "blocked", blockers: blockers as string[] };
  return { status: "unknown", blockers: [PROVIDER_ELIGIBILITY_MISSING] };
}
