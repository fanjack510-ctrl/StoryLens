#!/usr/bin/env node
/**
 * Generate UI audit contact sheet, coverage report, and ZIP.
 * Scans artifacts/ui-audit-work and docs/ui-audit-screen-inventory.md
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "../..");
const WORK = path.join(REPO, "artifacts", "ui-audit-work");
const SHOTS = path.join(WORK, "screenshots");
const INVENTORY = path.join(REPO, "docs", "ui-audit-screen-inventory.md");
const ZIP_OUT = path.join(REPO, "artifacts", "StoryLens_UI_Audit_0.1.0.zip");
const VERSION = "0.1.0";

const SECRET_RE =
  /sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|api[_-]?key["'\s:=]+[A-Za-z0-9_-]{12,}/gi;

function ensure() {
  fs.mkdirSync(WORK, { recursive: true });
  fs.mkdirSync(SHOTS, { recursive: true });
}

function listPngs() {
  if (!fs.existsSync(SHOTS)) return [];
  return fs
    .readdirSync(SHOTS)
    .filter((f) => f.toLowerCase().endsWith(".png"))
    .sort();
}

function parseInventoryExpected() {
  const text = fs.readFileSync(INVENTORY, "utf8");
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith("|")) continue;
    const cells = line.split("|").map((c) => c.trim());
    if (cells.length < 7) continue;
    const id = cells[1];
    const file = cells[6];
    const shot = cells[5];
    if (!id || id === "编号" || id.startsWith("---")) continue;
    if (!file || file === "—" || file === "-" || file === "文件名") {
      rows.push({ id, file: null, expected: shot.startsWith("是"), status: "not_implemented", label: cells[2] });
      continue;
    }
    const name = file.replace(/`/g, "");
    rows.push({
      id,
      file: name,
      expected: true,
      status: "expected",
      label: cells[2],
    });
  }
  return rows;
}

function scanSecrets(dir) {
  const hits = [];
  const walk = (p) => {
    for (const ent of fs.readdirSync(p, { withFileTypes: true })) {
      const full = path.join(p, ent.name);
      if (ent.isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.(json|jsonl|html|md|txt|log|csv)$/i.test(ent.name)) continue;
      const body = fs.readFileSync(full, "utf8");
      if (SECRET_RE.test(body)) {
        hits.push(full);
      }
      SECRET_RE.lastIndex = 0;
    }
  };
  walk(dir);
  return hits;
}

function writeContactSheet(pngs) {
  const cards = pngs
    .map(
      (f) => `
    <figure class="card">
      <a href="screenshots/${f}" target="_blank" rel="noopener">
        <img src="screenshots/${f}" alt="${f}" loading="lazy" />
      </a>
      <figcaption>${f}</figcaption>
    </figure>`,
    )
    .join("\n");
  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>StoryLens UI Audit Contact Sheet ${VERSION}</title>
  <style>
    :root { --bg:#f6f3ee; --ink:#1c1917; --muted:#78716c; --line:#e7e5e4; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: linear-gradient(180deg,#faf8f5,#efeae2); color:var(--ink); }
    header { padding: 28px 32px 12px; border-bottom:1px solid var(--line); background:rgba(255,255,255,.7); }
    h1 { margin:0 0 6px; font-size:28px; letter-spacing:.02em; }
    p { margin:0; color:var(--muted); }
    .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; padding:24px 32px 48px; }
    .card { margin:0; background:#fff; border:1px solid var(--line); border-radius:10px; overflow:hidden; }
    .card img { display:block; width:100%; height:160px; object-fit:cover; object-position:top; background:#ddd; }
    figcaption { padding:8px 10px 12px; font-size:12px; word-break:break-all; color:var(--muted); }
  </style>
</head>
<body>
  <header>
    <h1>StoryLens UI Audit · ${VERSION}</h1>
    <p>共 ${pngs.length} 张截图 · viewport 1440×900 · zh-CN · Asia/Shanghai · 确定性 Mock</p>
  </header>
  <div class="grid">${cards}</div>
</body>
</html>`;
  fs.writeFileSync(path.join(WORK, "contact-sheet.html"), html, "utf8");
}

function writeCoverage(inventory, pngs) {
  const have = new Set(pngs);
  const lines = [
    `# StoryLens UI 覆盖报告 ${VERSION}`,
    "",
    `- 生成时间：${new Date().toISOString()}`,
    `- 截图目录文件数：${pngs.length}`,
    `- 清单行数：${inventory.length}`,
    "",
    "| 编号 | 标签 | 期望文件 | 状态 |",
    "|---|---|---|---|",
  ];
  let captured = 0;
  let missing = 0;
  let notImpl = 0;
  for (const row of inventory) {
    if (!row.file) {
      notImpl += 1;
      lines.push(`| ${row.id} | ${row.label} | — | not_implemented |`);
      continue;
    }
    if (have.has(row.file)) {
      captured += 1;
      lines.push(`| ${row.id} | ${row.label} | \`${row.file}\` | captured |`);
    } else {
      missing += 1;
      lines.push(`| ${row.id} | ${row.label} | \`${row.file}\` | missing |`);
    }
  }
  const extra = pngs.filter((f) => !inventory.some((r) => r.file === f));
  lines.push("", "## 汇总", "");
  lines.push(`- captured: ${captured}`);
  lines.push(`- missing: ${missing}`);
  lines.push(`- not_implemented: ${notImpl}`);
  lines.push(`- extra screenshots: ${extra.length}`);
  if (extra.length) {
    lines.push("", "## 清单外截图", "");
    for (const f of extra) lines.push(`- \`${f}\``);
  }
  fs.writeFileSync(path.join(WORK, "coverage-report.md"), lines.join("\n"), "utf8");
  return { captured, missing, notImpl, extra: extra.length };
}

function writeScreenshotList(pngs) {
  const md = [
    `# 截图清单 ${VERSION}`,
    "",
    `| # | 文件名 | 大小 |`,
    `|---|---|---|`,
    ...pngs.map((f, i) => {
      const size = fs.statSync(path.join(SHOTS, f)).size;
      return `| ${i + 1} | \`${f}\` | ${size} |`;
    }),
  ].join("\n");
  fs.writeFileSync(path.join(WORK, "screenshot-list.md"), md, "utf8");
}

function writeRunbook() {
  const md = `# StoryLens UI Audit 运行说明（${VERSION}）

## 环境

- Windows 10/11
- Node.js 20+
- Playwright（Edge channel）
- 仓库根目录：\`D:\\\\Dstorylens-wt-ui-audit\`

## 一键运行

\`\`\`powershell
cd D:\\\\Dstorylens-wt-ui-audit
.\\\\scripts\\\\ui-audit\\\\run-ui-audit.ps1
\`\`\`

## 分步

\`\`\`powershell
cd apps\\\\desktop
npm install
npx playwright install msedge
# 清空工作目录后截图
Remove-Item -Recurse -Force ..\\\\..\\\\artifacts\\\\ui-audit-work -ErrorAction SilentlyContinue
npx playwright test --config playwright.ui-audit.config.ts
cd ..\\\\..
node scripts/ui-audit/pack-ui-audit.mjs
\`\`\`

## 输出

- 工作目录：\`artifacts/ui-audit-work/\`
- 压缩包：\`artifacts/StoryLens_UI_Audit_0.1.0.zip\`

## 约束

- 使用确定性 Mock，不调用真实阿里云。
- API Key 不得出现在截图、HTML、JSON、日志与 ZIP 明文中。
- 导入样本为虚构文本。
`;
  fs.writeFileSync(path.join(WORK, "RUN.md"), md, "utf8");
}

function copyDocs() {
  fs.copyFileSync(INVENTORY, path.join(WORK, "ui-audit-screen-inventory.md"));
  const pageList = `# 页面清单 ${VERSION}

| 路由 | 页面 |
|---|---|
| \`/\` | HomePage → /library |
| \`/library\` | LibraryPage |
| \`/workspace\` | WorkspaceLandingPage |
| \`/books/:bookId\` | BookRoutePage |
| \`/tasks\` | TasksPage |
| \`/analysis-runs/:runId/results\` | AnalysisResultsShellPage |
| \`/cases\` | CasesPage |
| \`/providers\` | ProvidersPage |
| \`/settings\` | SettingsPage |
`;
  fs.writeFileSync(path.join(WORK, "page-list.md"), pageList, "utf8");
}

function zipPackage() {
  if (fs.existsSync(ZIP_OUT)) fs.unlinkSync(ZIP_OUT);
  const staging = path.join(REPO, "artifacts", `_zip_staging_${VERSION}`);
  fs.rmSync(staging, { recursive: true, force: true });
  fs.mkdirSync(staging, { recursive: true });
  const rootName = `StoryLens_UI_Audit_${VERSION}`;
  const dest = path.join(staging, rootName);
  fs.cpSync(WORK, dest, { recursive: true });
  // Prefer tar (handles locks better than Compress-Archive on Windows).
  try {
    execSync(`tar -a -c -f "${ZIP_OUT}" -C "${staging}" "${rootName}"`, {
      stdio: "inherit",
      shell: true,
    });
  } catch {
    const ps = `Compress-Archive -Path '${dest.replace(/'/g, "''")}' -DestinationPath '${ZIP_OUT.replace(/'/g, "''")}' -Force`;
    execSync(`powershell -NoProfile -Command "${ps}"`, { stdio: "inherit" });
  }
  fs.rmSync(staging, { recursive: true, force: true });
}

function main() {
  ensure();
  const pngs = listPngs();
  const inventory = parseInventoryExpected();
  writeContactSheet(pngs);
  const summary = writeCoverage(inventory, pngs);
  writeScreenshotList(pngs);
  writeRunbook();
  copyDocs();

  const secretHits = scanSecrets(WORK);
  if (secretHits.length) {
    console.error("SECRET LEAK DETECTED in:");
    for (const h of secretHits) console.error(" -", h);
    process.exit(2);
  }

  const meta = {
    version: VERSION,
    generated_at: new Date().toISOString(),
    screenshot_count: pngs.length,
    ...summary,
    zip: ZIP_OUT,
  };
  fs.writeFileSync(path.join(WORK, "audit-meta.json"), JSON.stringify(meta, null, 2));
  zipPackage();
  console.log(JSON.stringify(meta, null, 2));
}

main();
