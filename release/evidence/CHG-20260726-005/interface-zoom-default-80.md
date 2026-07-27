# CHG-20260726-005 — Default interface zoom 80%

```text
Product decision (manual acceptance feedback)
Default interface zoom changed from 100% to 80%.
Existing valid user preferences are preserved.
Reset and Ctrl+0 restore the product default of 80%.
100% remains a selectable preset.
Target candidate：1.1.0-rc.3
```

## Behavior

```text
No saved value / empty / illegal → 80
Saved 80/90/100/110/125/150 → keep saved
Reset button：恢复默认（80%）
Ctrl+0 → 80
```

## Verification

```text
vitest interfaceZoom + SettingsAppearanceZoom + shortcuts：13 passed
typecheck：pass
vite production build：pass
git diff --check：pass
```

## RC3 rebuild (includes default 80%)

```text
Installer��dist\release\StoryLens_1.1.0-rc.3_x64-setup.exe
SHA-256��4A15EE5265A0978E2D83029C190C7ECFF023003D7A88B5F2F064409D11983FA8
Public HEAD��a0668b050bc8ca0ba7e02904047630e00535a570
Formal VERSION��1.0.5
```
