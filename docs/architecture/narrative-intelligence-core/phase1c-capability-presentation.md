# Phase 1C Capability Presentation Contract (Frontend)

Agent I presentation helpers and isolated components.

## Helper API

```ts
hasCapability(key)                 // store: backend allowed only
getCapabilityDecision(key)         // store decision or null
getCapabilityPresentation(key, decision?, metadata?)
```

## Presentation states

| State | Typical reasonCode | disabled | upgrade CTA | preview CTA |
|-------|--------------------|----------|-------------|-------------|
| `available` | `CAPABILITY_AVAILABLE` | false | no | no |
| `preview` | `CAPABILITY_PREVIEW_ONLY` | depends on allowed | no | yes |
| `not_licensed` | `CAPABILITY_NOT_LICENSED` | true | yes* | no |
| `not_shipped` | `CAPABILITY_NOT_SHIPPED` | true | no | no |
| `quota_exceeded` | `CAPABILITY_QUOTA_EXCEEDED` | true | no | no |
| `license_expired` | `CAPABILITY_LICENSE_EXPIRED` | true | yes* | no |
| `license_invalid` | `CAPABILITY_LICENSE_INVALID` | true | yes* | no |
| `offline_unavailable` | `CAPABILITY_OFFLINE_NOT_ALLOWED` | true | no | no |
| `unknown` | `CAPABILITY_UNKNOWN` / missing | true | no | no |

\* Upgrade CTA suppressed for `narrative_asset_library` (foundation, not paywalled).

## Copy rules

Avoid vague “VIP不足”. Prefer:

- “该功能尚未发布”
- “当前授权不包含整书分析”
- “本次使用额度已用完”
- “离线状态下无法验证授权”
- “授权已过期，请续期后再使用”
- “授权无效，请重新激活后再试”

## Return shape

- `label`
- `message`
- `disabled`
- `showUpgradeAction`
- `showPreviewAction`
- `supportedModes`

## Components (`features/capability`)

| Component | Role |
|-----------|------|
| `CapabilityGate` | Shows reason/preview; never silent-hide only |
| `CapabilityStatusBadge` | Compact state badge; foundation tagged separately |
| `ProFeaturePreviewCard` | Preview vs available card |
| `CapabilityReasonPanel` | Accessible reason text (`aria-live`) |

Constraints:

- Deep/light themes via CSS tokens + `data-theme`
- Keyboard focusable (`tabIndex`, Enter/Space on gate)
- Disabled state explicit via `data-disabled` / `aria-disabled`
- Not wired to formal whole-book page or main nav
- Mock/Story testable via Vitest + Testing Library

## Pricing

Presentation and Store contain **no** real commercial prices.
