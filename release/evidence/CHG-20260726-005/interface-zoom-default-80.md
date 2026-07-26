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
