# Windows RC Build Log

Started: 2026-07-26T12:38:27.5158879+08:00
Finished: 2026-07-26T12:45:40.6976238+08:00
RC Version: 1.1.0-rc.3
Formal VERSION restored to: 1.0.5
Private Engine: D:\Dstorylens-private-engine-wt-phase2br1-integration
STORYLENS_RC_CANDIDATE: 1
VITE_PRO_NATIVE_OVERVIEW_ENABLED (RC bake): true
Live Provider: NO

## Log

- 2026-07-26T12:38:27.5395201+08:00  STEP 2.7 RC build start
- 2026-07-26T12:38:27.8676260+08:00  Formal VERSION=1.0.5 RC=1.1.0-rc.3
- 2026-07-26T12:38:27.8766232+08:00  PrivateEnginePath=D:\Dstorylens-private-engine-wt-phase2br1-integration
- 2026-07-26T12:38:27.8926251+08:00  Install Private Engine editable into build venv
- 2026-07-26T12:38:55.8246466+08:00  Temporary version override -> 1.1.0-rc.3
- 2026-07-26T12:38:57.1614585+08:00  Archive already has StoryLens_1.1.0-rc.2_x64-setup.exe; leave untouched
- 2026-07-26T12:38:57.1644625+08:00  Invoke build_windows_release.ps1 (RC candidate mode; Native Overview UI baked on)
- 2026-07-26T12:45:40.5198882+08:00  build-summary.json present
- 2026-07-26T12:45:40.5258863+08:00  {
- 2026-07-26T12:45:40.5288543+08:00      "started_at":  "2026-07-26T12:38:57.1974555+08:00",
- 2026-07-26T12:45:40.5308473+08:00      "version":  "1.1.0-rc.3",
- 2026-07-26T12:45:40.5328442+08:00      "frontend":  "ok",
- 2026-07-26T12:45:40.5348438+08:00      "sidecar":  "ok",
- 2026-07-26T12:45:40.5358440+08:00      "tauri":  "ok",
- 2026-07-26T12:45:40.5378456+08:00      "updater_artifacts":  "skipped_no_secret",
- 2026-07-26T12:45:40.5398447+08:00      "outputs":  [
- 2026-07-26T12:45:40.5418445+08:00                      "D:\\Dstorylens-wt-narrative-phase2br1-integration\\dist\\release\\StoryLens_1.1.0-rc.3_x64-setup.exe",
- 2026-07-26T12:45:40.5438458+08:00                      "D:\\Dstorylens-wt-narrative-phase2br1-integration\\dist\\release\\storylens-api.exe"
- 2026-07-26T12:45:40.5448437+08:00                  ],
- 2026-07-26T12:45:40.5468444+08:00      "errors":  [
- 2026-07-26T12:45:40.5488473+08:00  
- 2026-07-26T12:45:40.5508442+08:00                 ],
- 2026-07-26T12:45:40.5528443+08:00      "rc_candidate":  true,
- 2026-07-26T12:45:40.5538474+08:00      "installer":  "D:\\Dstorylens-wt-narrative-phase2br1-integration\\dist\\release\\StoryLens_1.1.0-rc.3_x64-setup.exe",
- 2026-07-26T12:45:40.5558445+08:00      "sidecar_in_release":  true,
- 2026-07-26T12:45:40.5568436+08:00      "finished_at":  "2026-07-26T12:45:36.4089744+08:00"
- 2026-07-26T12:45:40.5588461+08:00  }
- 2026-07-26T12:45:40.5598472+08:00  RC build finished OK
- 2026-07-26T12:45:40.5628452+08:00  Restoring formal VERSION files via git checkout
