# MANUAL INSTALLED ACCEPTANCE — StoryLens 1.1.1-rc.1

Installer:
`D:\Dstorylens-wt-narrative-phase2br1-integration\dist\release\StoryLens_1.1.1-rc.1_x64-setup.exe`

SHA-256: 7C7348576397A1DC08DE7CEF6831F0036A332F7308DF10288C7F38AF9BD56916

This step does **not** auto-install. Formal AppData / GUI / Sidecar remain untouched until you install.

## Mode A — Fresh install

1. Fully uninstall StoryLens and delete `%LOCALAPPDATA%\StoryLens` if validating clean state.
2. Install RC1 from the path above.
3. Confirm UI/product version shows `1.1.1-rc.1`.
4. Confirm local service health and Provider config loads.
5. Confirm default API Key is empty.
6. Import TXT / DOCX / EPUB smoke (no Provider required).
7. Confirm single-chapter entry works; whole-book / native overview / independent Journey entries stay hidden.
8. Confirm Sidecar starts from install directory; logs show V2 config `source=bundled`.
9. Confirm no config-missing / `[0,100]` fallback messages.

## Mode B — Existing results (DB copy or explicit test DB)

1. Open existing Journey results without auto Provider calls.
2. Speed curve remains `95/80/50/80/80/50/30/65/30`.
3. `pacing_fit` is no longer systematically all `90`.
4. Config provenance normal; null fit shows unavailable/safe UI.
5. Do **not** auto batch-rewrite old runs.
6. Formal `--apply` repair only with your explicit approval.

Reply `PASS` / `FAIL` after manual acceptance. Only then may CHG-021 become `verified`.