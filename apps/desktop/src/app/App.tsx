import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { DesktopBootstrap } from "../components/desktop/DesktopBootstrap";
import { queryClient } from "./queryClient";
import { router } from "./router";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DesktopBootstrap>
        <RouterProvider router={router} />
      </DesktopBootstrap>
    </QueryClientProvider>
  );
}
