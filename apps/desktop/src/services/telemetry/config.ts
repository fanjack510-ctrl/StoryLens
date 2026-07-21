export type TelemetryBuildConfig = {
  endpoint: string | null;
  projectKey: string | null;
};

export function readTelemetryBuildConfig(
  env: ImportMetaEnv = import.meta.env,
): TelemetryBuildConfig {
  const endpoint = (env.VITE_TELEMETRY_ENDPOINT ?? "").trim();
  const projectKey = (env.VITE_TELEMETRY_PROJECT_KEY ?? "").trim();
  return {
    endpoint: endpoint.length > 0 ? endpoint : null,
    projectKey: projectKey.length > 0 ? projectKey : null,
  };
}

export function isTelemetryTransportConfigured(config: TelemetryBuildConfig): boolean {
  return Boolean(config.endpoint && config.projectKey);
}
