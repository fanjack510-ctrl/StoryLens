/**
 * Write public frontend build identity into dist/ after vite build.
 * No secrets, no absolute local paths.
 */
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(__dirname, "..");
const repoRoot = resolve(desktopRoot, "../..");
const distDir = resolve(desktopRoot, "dist");
const indexPath = resolve(distDir, "index.html");
const metaPath = resolve(distDir, "storylens-frontend-build.json");

if (!existsSync(indexPath)) {
  console.error("write-dist-build-meta: dist/index.html missing");
  process.exit(1);
}

function gitHead() {
  try {
    return execSync("git rev-parse HEAD", { cwd: repoRoot, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

function appVersion() {
  try {
    const pkg = JSON.parse(readFileSync(resolve(desktopRoot, "package.json"), "utf8"));
    return typeof pkg.version === "string" ? pkg.version : "unknown";
  } catch {
    return "unknown";
  }
}

const meta = {
  source_commit: gitHead(),
  build_time: new Date().toISOString(),
  application_version: appVersion(),
};

writeFileSync(metaPath, `${JSON.stringify(meta, null, 2)}\n`, "utf8");
console.log(
  `write-dist-build-meta: source_commit=${meta.source_commit} build_time=${meta.build_time}`,
);
