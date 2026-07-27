import { useEffect } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { DesktopBootstrap } from "../components/desktop/DesktopBootstrap";
import { useInterfaceZoomShortcuts } from "../hooks/useInterfaceZoomShortcuts";
import { applyInterfaceZoom } from "../lib/interfaceZoom";
import { onApiBaseChange } from "../services/apiClient";
import { useUiStore } from "../stores/uiStore";
import { queryClient } from "./queryClient";
import { router } from "./router";

function InterfaceZoomBootstrap() {
  useInterfaceZoomShortcuts();

  useEffect(() => {
    // One-shot: promote early CSS zoom to Tauri Webview.setZoom when available.
    void applyInterfaceZoom(useUiStore.getState().interfaceZoom);
  }, []);

  return null;
}

function ApiBaseQueryBridge() {
  useEffect(() => {
    return onApiBaseChange(() => {
      void queryClient.invalidateQueries();
    });
  }, []);
  return null;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DesktopBootstrap>
        <ApiBaseQueryBridge />
        <InterfaceZoomBootstrap />
        <RouterProvider router={router} />
      </DesktopBootstrap>
    </QueryClientProvider>
  );
}
