import { useEffect } from "react";
import {
  DEFAULT_INTERFACE_ZOOM,
  shouldIgnoreInterfaceZoomShortcut,
  stepInterfaceZoom,
} from "../lib/interfaceZoom";
import { useUiStore } from "../stores/uiStore";

/** Ctrl/Cmd + / - / = / 0 → discrete interface zoom. */
export function useInterfaceZoomShortcuts(): void {
  const setInterfaceZoom = useUiStore((s) => s.setInterfaceZoom);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      if (shouldIgnoreInterfaceZoomShortcut(event.target)) return;

      const key = event.key;
      const code = event.code;
      const current = useUiStore.getState().interfaceZoom;

      if (key === "0" || code === "Digit0" || code === "Numpad0") {
        event.preventDefault();
        void setInterfaceZoom(DEFAULT_INTERFACE_ZOOM);
        return;
      }

      const zoomIn =
        key === "+" ||
        key === "=" ||
        code === "Equal" ||
        code === "NumpadAdd";
      const zoomOut = key === "-" || key === "_" || code === "Minus" || code === "NumpadSubtract";

      if (zoomIn) {
        event.preventDefault();
        void setInterfaceZoom(stepInterfaceZoom(current, 1));
        return;
      }
      if (zoomOut) {
        event.preventDefault();
        void setInterfaceZoom(stepInterfaceZoom(current, -1));
      }
    };

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [setInterfaceZoom]);
}
