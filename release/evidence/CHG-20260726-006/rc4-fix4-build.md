# RC4 FIX-4 build record

- Public HEAD: `eace86f0e6b276fdece90f86a35f03a3f58f33c3`
- Private HEAD: `30d8dad8cd649e832999874f7bf16cc1661cf221`
- Installer: `D:\Dstorylens-wt-narrative-phase2br1-integration\dist\release\StoryLens_1.1.0-rc.4_x64-setup.exe`
- Size: 42096724 bytes
- SHA-256: `F17FE350CF36EA1BDABCEA31C49C1A3F6987E3217E95365E1DA0ADEC1B842BB8`
- Build started: 2026-07-26T20:16:23+08:00
- Build finished: 2026-07-26T20:22:50+08:00
- Formal VERSION after restore: `1.0.5`

## Uninstall data protection

User DB path (`paths.user_data_root`): `%LOCALAPPDATA%\StoryLens` — separate from NSIS application install tree.
Tauri NSIS `installMode=currentUser` uninstall removes the app bundle only; it does not delete the user data root.
Live uninstall/reinstall GUI smoke remains a manual acceptance step.
