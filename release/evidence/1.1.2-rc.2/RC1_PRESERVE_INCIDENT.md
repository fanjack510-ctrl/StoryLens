# RC.1 Preserve Incident (during 1.1.2-rc.2 build)

## Fact

- Before RC.2 build, `StoryLens_1.1.2-rc.1_x64-setup.exe` SHA-256 was recorded as  
  `2C9ED3B8E898118391B56F7A297F96B9CFB8A9951C1226C851C5B7C1AEF1F61F`.
- `scripts/build_windows_rc.ps1` previously copied prior installers into `dist/release/archive/`.
- `scripts/build_windows_release.ps1` then executes  
  `Get-ChildItem $ReleaseDir | Remove-Item -Recurse -Force`, wiping **all** of `dist/release`,
  including the `archive/` subdirectory.
- After RC.2 collect, the RC.1 binary was no longer on disk (deep search found no
  `StoryLens_1.1.2-rc.1*` copy). Hash evidence remains in
  `release/evidence/1.1.2-rc.2/RC1_PRESERVED_HASH.txt`.

## Mitigation applied in this change

- RC.2 installer immediately copied to  
  `D:\StoryLens-Local-Evidence\installer-archive\StoryLens_1.1.2-rc.2_x64-setup.exe`.
- `build_windows_rc.ps1` updated to archive prior installers to  
  `D:\StoryLens-Local-Evidence\installer-archive` **outside** `dist/release`.

## Impact

- RC.1 binary cannot be redistributed from this machine unless recovered from another
  backup not found in this session.
- RC.2 build/install-state verification itself PASS; formal AppData DB writes remained 0.
