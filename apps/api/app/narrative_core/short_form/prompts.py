"""Prompts for 短篇精读. Three, each asked to do one thing.

Every worked example below names a story that does not exist. That is not a style choice: the
whole-book breakdown engine was built with examples lifted from 《一梦如初》 and then validated
against 《一梦如初》, so the prompt was handing the model the answers — and the contamination is
invisible from the output, because a seeded answer looks exactly like a good reading.
"""

from __future__ import annotations

__all__ = [
    "SEGMENT_INSTRUCTION",
    "RESPLIT_INSTRUCTION",
    "READ_INSTRUCTION",
    "SHAPE_INSTRUCTION",
    "GENRE_LENS",
]


SEGMENT_INSTRUCTION = """把这篇小说切成若干**场景段**。

**按场景切，不要按字数平均分。** 一个场景段的判据是下面任意一条发生了：
- 地点变了
- 在场的人变了
- 时间跳了（第二天 / 三年后 / 回忆插入）
- 目标变了：这一段之后，主角要的东西不一样了

一段通常 500–1200 字，全篇常见 15–30 段。**宁可段落长一点，也不要把一个连续场景切开。**

但 **不要出现超过 2000 字的段**。一段读下来如果换过地点、换过在场的人、或者跳过时间，
它就已经不是一个场景了——按上面四条判据在那里再断一刀。

每段给出：
- `paragraph_start` / `paragraph_end`：该段的自然段编号区间（正文里每段前有 `[p:N]` 标记）
- `why`：为什么在这里断，≤20 字，写上面四条里的哪一条

**首尾相接、覆盖全文、不重叠。** 第一段从 1 开始，最后一段到最后一个自然段。
只输出 JSON：`{"segments": [{"paragraph_start": 1, "paragraph_end": 6, "why": ""}]}`"""


RESPLIT_INSTRUCTION = """下面这些段太长了——一段里装了不止一个场景。请把每一段再切开。

判据和上一次一样，任意一条发生了就断：地点变了 / 在场的人变了 / 时间跳了 / 目标变了。

- 每段切成 2–4 小段，切完每小段大致 500–1200 字
- `ends` 填**该段内部的断点**：断点处的自然段号，表示「这个自然段是一小段的最后一段」
- 不要填该段的最后一个自然段号——结尾是自动的
- 如果这一段确实通篇是一个连续场景，`ends` 给空数组，不要硬切

只输出 JSON：`{"splits": [{"index": 7, "ends": [210, 250]}]}`"""


READ_INSTRUCTION = """逐段填写这张拆稿表。

**`前文` 里是这一批之前已经读过的段落。** 它在那里只为三件事，请逐段核对：

1. **重复**：这一段有没有出现前面出现过的说法、物件、动作？
   一句话说第二遍就不再是一句话了——第一次是台词，第二次是这两个人之间的暗号。
2. **推翻**：这一段有没有让读者发现「前面以为的不是那么回事」？
   如果有，`craft` 要写清**读者原来以为的是什么**，不能只写「揭示了真相」。
3. **没有话的时刻**：这一段最重的地方，会不会恰恰是**没人说话**——
   她一句话都没说、他站着没动、沉默了很久。这种地方最容易被写成「揭示了某某」而漏掉，
   `craft` 要把那个动作本身说出来。

每一段给出七项：

- `phase` 故事进展：这一段把故事推到了哪一步，≤14 字。
  好例子：「陷入危机」「第一次尝试失败」「身份被揭穿」
  坏例子：「发展」「过渡」「情节推进」——这些对任何一段都成立
- `setting` 地点/人物：`地点/出场的人`，例如「老屋/女主、母亲、债主」
- `beats` 事件/冲突：这一段发生的事，按顺序，一条一件，3–6 条
- `craft` 学习之处：**这一手做了什么、代价是什么、留下了什么新问题**，40–80 字。
  好例子：「再来一次，解决了上次的困难，但暴露了新漏洞，结局的不确定性反而增加了。
  此时主角的勇气还是不够」
  坏例子：「描写生动」「节奏紧凑」「人物形象鲜明」——这是评语，不是写法
- `emotion_note` 读者此刻在哪：≤24 字，写状态不写评价。
  好例子：「至暗时刻：看不到出路」「反转：以为的敌人其实在护着他」「获得胜利」
- `emotion_direction`：`up`（读者更痛快/更安心）、`down`（更揪心/更失落）、`flat`（持平）

**允许留空。** 某一段实在没有值得学的地方，`craft` 就填空字符串——
凑一句「这里写得不错」比留空更糟。

- `callback` 这一段呼应了前面的哪一处：≤30 字，写「呼应第 N 段的某某」。
  **前面没有可呼应的就留空字符串**，不要为了填而攀扯。

只输出 JSON：`{"segments": [{"index": 1, "phase": "", "setting": "", "beats": [],
"craft": "", "emotion_note": "", "emotion_direction": "flat", "callback": ""}]}`"""


SHAPE_INSTRUCTION = """给这篇小说做一个整体判断。

- `one_line` 一句话梗概：谁、想要什么、最后怎样。≤60 字，要有情节，不要写「一个关于成长的故事」
- `beats` 起承转合**恰好四段**，按**段号**给区间（`segment_start` / `segment_end`），
  四段首尾相接、覆盖全篇、不重叠。分界按叙事功能划，不按段数平均分。
  **但任何一段都不该占到全篇一半以上。** 如果「合」看起来要吃掉后半本，
  说明「转」的位置找早了——真正的转折通常在你以为的那一处之后。
  每段给 `title`（一句话，本身要有情节）和 `summary`（60–120 字）
  好标题例子：「顶下濒临倒闭的旧书店，靠夜市摆摊熬过第一个冬天」
  坏标题例子：「开端」「第一阶段」
- **`反复出现` 是引擎逐字比对原文找出来的**，不是判断，是事实：这些说法在多个段落里出现过。
  哪几条真的是「梗」——被有意重复、第二次出现时意思变了——由你判断，
  在 `beats` 的 `summary` 里点出来。**不是梗的就不要提**，那只是普通的用词。

- `emotion_up` / `emotion_down`：主线情绪的上行段与下行段，各 2–4 条。
  每条写「在哪一段、什么让读者松/紧」。
  **每条写成一句话**，形如「第 6–7 段：面对逼婚，她当众撕掉了合同，一波小爽」。
  不要返回 `{"segment": ..., "note": ...}` 这样的对象，直接给字符串。
  **下行段要写清它在为后面的哪一次上行积欠**——只有下行没有兑现，读者会弃文。

只输出 JSON：`{"one_line": "", "beats": [], "emotion_up": [], "emotion_down": []}`"""


#: What "打动人" means differs by genre, and the corpus's craft notes are written in each
#: genre's own terms. One line, appended to the reading prompt — the short-form entry asks the
#: user for a single genre rather than the five profile axes a long novel needs.
GENRE_LENS: dict[str, str] = {
    "悬疑": "这是悬疑。看的是：什么时候给线索、什么时候瞒、读者比主角多知道还是少知道。",
    "言情": "这是言情。看的是：身份差、误会、以及一方先动心而另一方不知道的那段时间。",
    "爽文": "这是爽文。看的是：立标与兑现——什么时候受屈、什么时候还回去、间隔多长。",
    "家庭伦理": "这是家庭伦理。看的是：谁欠谁、道德立场怎么挪、旁观者站哪边。",
    "奇幻设定": "这是设定驱动。看的是：规则什么时候讲清、什么时候被打破、代价谁付。",
    "现实题材": "这是现实题材。看的是：具体的处境细节、普通人能做到的选择、以及沉默的时刻。",
}


def genre_lens(genre: str) -> str:
    return GENRE_LENS.get(genre.strip(), "")
