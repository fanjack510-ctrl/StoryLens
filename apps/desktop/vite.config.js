import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const rootDir = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(resolve(rootDir, "package.json"), "utf-8"));

export default defineConfig({
  plugins: [react()],
  define: {
    __STORYLENS_APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: { port: 1420, strictPort: true },
  test: { environment: "jsdom", setupFiles: "./src/testSetup.ts" },
});
