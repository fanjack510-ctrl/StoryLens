import { useAppVersion } from "../../lib/useAppVersion";

/** Compact About block — same version source as AppShell / Settings. */
export function AboutAppVersion() {
  const version = useAppVersion();
  return (
    <p data-testid="about-app-version">
      StoryLens {version}
    </p>
  );
}
