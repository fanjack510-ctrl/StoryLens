import { useEffect, useState } from "react";
import {
  formatAppVersionLabel,
  resolveAppVersion,
  UNKNOWN_VERSION_LABEL,
} from "./appVersion";

/** Shared hook so AppShell / Settings / About show the same resolved version. */
export function useAppVersion(): string {
  const [version, setVersion] = useState<string>(UNKNOWN_VERSION_LABEL);

  useEffect(() => {
    let cancelled = false;
    void resolveAppVersion().then((resolved) => {
      if (!cancelled) {
        setVersion(formatAppVersionLabel(resolved));
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}
