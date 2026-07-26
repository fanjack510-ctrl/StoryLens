# Windows RC Build Log

Started: 2026-07-26T12:51:46.3414228+08:00
Finished: 2026-07-26T12:59:44.2988010+08:00
RC Version: 1.1.0-rc.3
Formal VERSION restored to: 1.0.5
Private Engine: D:\Dstorylens-private-engine-wt-phase2br1-integration
STORYLENS_RC_CANDIDATE: 1
VITE_PRO_NATIVE_OVERVIEW_ENABLED (RC bake): true
Live Provider: NO

## Log

- 2026-07-26T12:51:46.3929729+08:00  STEP 2.7 RC build start
- 2026-07-26T12:51:47.0745745+08:00  Formal VERSION=1.0.5 RC=1.1.0-rc.3
- 2026-07-26T12:51:47.1185720+08:00  PrivateEnginePath=D:\Dstorylens-private-engine-wt-phase2br1-integration
- 2026-07-26T12:51:47.1585742+08:00  Install Private Engine editable into build venv
- 2026-07-26T12:52:19.7980604+08:00  Temporary version override -> 1.1.0-rc.3
- 2026-07-26T12:52:21.1748497+08:00  Archiving prior installer StoryLens_1.1.0-rc.3_x64-setup.exe
- 2026-07-26T12:52:21.2338490+08:00  Invoke build_windows_release.ps1 (RC candidate mode; Native Overview UI baked on)
- 2026-07-26T12:59:44.0459721+08:00  build-summary.json present
- 2026-07-26T12:59:44.0623605+08:00  {
- 2026-07-26T12:59:44.0673601+08:00      "started_at":  "2026-07-26T12:52:21.2858510+08:00",
- 2026-07-26T12:59:44.0703593+08:00      "version":  "1.1.0-rc.3",
- 2026-07-26T12:59:44.0743684+08:00      "frontend":  "ok",
- 2026-07-26T12:59:44.0783594+08:00      "sidecar":  "ok",
- 2026-07-26T12:59:44.0810029+08:00      "tauri":  "ok",
- 2026-07-26T12:59:44.0839864+08:00      "updater_artifacts":  "skipped_no_secret",
- 2026-07-26T12:59:44.0869873+08:00      "outputs":  [
- 2026-07-26T12:59:44.0889851+08:00                      "D:\\Dstorylens-wt-narrative-phase2br1-integration\\dist\\release\\StoryLens_1.1.0-rc.3_x64-setup.exe",
- 2026-07-26T12:59:44.0919854+08:00                      "D:\\Dstorylens-wt-narrative-phase2br1-integration\\dist\\release\\storylens-api.exe"
- 2026-07-26T12:59:44.0969861+08:00                  ],
- 2026-07-26T12:59:44.1000371+08:00      "errors":  [
- 2026-07-26T12:59:44.1025769+08:00  
- 2026-07-26T12:59:44.1054770+08:00                 ],
- 2026-07-26T12:59:44.1076890+08:00      "rc_candidate":  true,
- 2026-07-26T12:59:44.1117026+08:00      "installer":  "D:\\Dstorylens-wt-narrative-phase2br1-integration\\dist\\release\\StoryLens_1.1.0-rc.3_x64-setup.exe",
- 2026-07-26T12:59:44.1137016+08:00      "sidecar_in_release":  true,
- 2026-07-26T12:59:44.1167003+08:00      "finished_at":  "2026-07-26T12:59:39.3497868+08:00"
- 2026-07-26T12:59:44.1187008+08:00  }
- 2026-07-26T12:59:44.1217015+08:00  RC build finished OK
- 2026-07-26T12:59:44.1267025+08:00  Restoring formal VERSION files via git checkout
