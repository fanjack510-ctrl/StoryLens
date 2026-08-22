import fs from "node:fs";
import { parseWholeBookV2 } from "./src/features/wholeBookV2/adapter";
import { buildPrintHtml } from "./src/features/wholeBookV2/printExport";

const d = parseWholeBookV2(JSON.parse(fs.readFileSync(process.argv[2], "utf-8")));
const html = buildPrintHtml(d);
fs.writeFileSync(process.argv[3], html, "utf-8");
console.log("bytes", html.length, "pages", (html.match(/class="page"/g) ?? []).length);
