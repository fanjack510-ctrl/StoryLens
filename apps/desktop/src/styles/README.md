# 样式：三层，从上往下用

改样式之前先读这一页。它不长，而且它记的是**已经踩过的坑**。

## 三层

```
tokens.css      设计令牌。颜色、字号、间距、圆角、控件高度。明暗两套主题都在这里。
global.css      应用外壳与全局元素。开头把令牌别名成 --accent / --line / --muted / --text / --surface。
<feature>.css   各功能自己的样式。只用令牌或别名，不写字面量。
```

**永远从上往下取值。** 需要一个颜色，先在 `tokens.css` 里找；找不到就在那里加一个，而不是在
功能样式里写一个十六进制。

## 为什么不能写死颜色

2026-08-23 的普查：16000 行 CSS 里有 1312 处颜色字面量，其中 **225 处的值和某个令牌完全相同**。
浅色模式下它们看不出任何区别——所以谁也没发现问题。深色模式下它们**全是错的**：

| 写死的值 | 出现次数 | 深色下应该是 |
|---|---|---|
| `#ffffff` | 113 | `#18211d`（`--color-bg-surface`） |
| `#2f6b57` | 96 | `#69a98e`（`--color-brand`） |
| `#f5f5f1` | 8 | `#111713`（`--color-bg-app`） |

也就是说，深色模式下有一百多处白底和近百处浅绿，全都停在浅色主题上。那次普查把其中 195 处
换回了令牌（按值完全相同替换，浅色渲染逐像素不变）。

## 一个真会咬人的坑：同一个值对应两个令牌

`#ffffff` 既是 `--color-bg-surface`（白色卡片底），也是 `--color-text-inverse`（品牌底上的白字）。
而这两个令牌在深色下**走向相反**：

```
              浅色        深色
bg-surface    #ffffff  →  #18211d     卡片底：变深
text-inverse  #ffffff  →  #111713     字：也变深，因为品牌色变浅了
```

所以按值盲换会把绿底按钮上的字变成「深色压浅绿」。按**属性**分：

* `background` / `border` / `outline` / `fill` → 用 `--color-bg-*`、`--color-border`、`--color-brand`
* `color` 在品牌底上 → 用 `--color-text-inverse`
* `color` 在普通底上 → 用 `--color-text-primary` / `-secondary` / `-tertiary`

## 别名那一层

`global.css` 顶上把令牌别名成短名字，供旧的功能样式使用：

```css
.app                     { --accent: var(--color-brand); … }
.app[data-theme="dark"]  { --accent: var(--color-brand); … }   /* 必须重新绑定 */
```

**两处都要写。** 别名如果只在浅色那一处声明，`var()` 会在那里就把值定死，深色主题再也够不着它。
新代码直接用 `--color-*`，不要再增加别名的使用面。

## 名字会骗人

`features/wholeBookV2Mock/wholeBookV2Mock.css` 听起来是演示页的样式，实际上
`WholeBookV2ReportView.tsx` 直接 import 它——**它是真正的全书报告页在用的**。那次普查差一点因为
名字把这份最大的（536 处字面量、100 处深色错）跳过去。

改任何名字带 mock / demo / prototype 的样式之前，先 grep 谁 import 了它。

## 验证

```bash
# 类型检查必须用 app 那份配置。根 tsconfig.json 是 "files": [] 的项目引用壳，
# 用它检查等于什么都没查——这条坑过一整晚。
npx tsc --noEmit -p tsconfig.app.json
```

深色模式的渲染要在**可见的浏览器窗口**里看。隐藏标签页里 CSS 过渡不推进、背景色重算被推迟，
`getComputedStyle` 读出来的东西不可信。
