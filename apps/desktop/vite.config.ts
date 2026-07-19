import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { port: 1420, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: "./src/testSetup.ts",
    exclude: ["e2e/**", "node_modules/**"],
  },
});
