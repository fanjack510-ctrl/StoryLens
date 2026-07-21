/** Update channel endpoints — independent manifests, shared pubkey. */

export type UpdateChannel = "stable" | "staging";

export const STABLE_UPDATE_ENDPOINT =
  "https://github.com/fanjack510-ctrl/StoryLens/releases/latest/download/latest.json";

/** Internal test channel only. Never used as the default for normal installs. */
export const STAGING_UPDATE_ENDPOINT =
  "https://github.com/fanjack510-ctrl/StoryLens/releases/download/staging/latest.json";

export const UPDATE_CHANNEL_ENDPOINTS: Record<UpdateChannel, string> = {
  stable: STABLE_UPDATE_ENDPOINT,
  staging: STAGING_UPDATE_ENDPOINT,
};

export function endpointForChannel(channel: UpdateChannel): string {
  return UPDATE_CHANNEL_ENDPOINTS[channel];
}

export function normalizeUpdateChannel(raw: unknown): UpdateChannel {
  return raw === "staging" ? "staging" : "stable";
}
