"""把 N 本书的技法归成共性条目——并且不许它编。

可复用技法是自由文本。「用一句反常识的话立住人物」（余罪）和「身份倒转制造情感爆点」
（我不是戏神）之间的关系，字符串匹配永远找不出来，只有读进去才知道两者都属于「用一次
认知冲突把人物钉住」。这是这一层存在的理由，也是它值得收费的理由。

同时这是整个功能最容易变成废话的地方。「这些书都很会写钩子」既正确又无用，而且无法证伪。
防住它的办法是**结构上不允许**：每一条共性都必须列出它引用的书和那本书里的具体技法名，
后端逐条核对——引用了不在这组里的书、或者那本书里没有的技法名，整条丢掉。

模型编不出通过校验的引用，因为它不知道哪些 id 会被接受。
"""

from __future__ import annotations

import json
from typing import Any

from app.narrative_core.common_patterns.aggregate import BookFacts

__all__ = ["MIN_BOOKS", "build_prompt", "parse_and_verify", "RESPONSE_SCHEMA"]

#: 少于两本没有「共性」可言——一本书的写法叫做它自己的写法。
MIN_BOOKS = 2

#: 一条共性至少要有几本书这么做。设成 2 而不是「多数」：十五本里有两本用同一招，
#: 对一个正在找可借鉴手法的人来说已经值得看一眼，而要求过半会把最有意思的少数派滤掉。
MIN_SUPPORT = 2

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["patterns"],
    "properties": {
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "what_they_do", "why_it_works", "instances"],
                "properties": {
                    "name": {"type": "string"},
                    "what_they_do": {"type": "string"},
                    "why_it_works": {"type": "string"},
                    "instances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["book_id", "technique_name"],
                            "properties": {
                                "book_id": {"type": "integer"},
                                "technique_name": {"type": "string"},
                                "how_this_book_does_it": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "not_shared": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["book_id", "what_only_this_one_does"],
                "properties": {
                    "book_id": {"type": "integer"},
                    "what_only_this_one_does": {"type": "string"},
                },
            },
        },
    },
}


def build_prompt(facts: list[BookFacts]) -> str:
    """喂给模型的东西：只有书号、书名、类型、范围，和技法原文。

    不给它评分、不给它排名、不给它「哪本更好」——共性视图回答的是「这些书共同做了什么」，
    不是「哪本写得好」。后者是评测的活，混进来会让这份结果变成一个没人要的排行榜。
    """
    usable = [f for f in facts if f.usable]
    lines: list[str] = []
    for f in usable:
        scope = (
            f"只读了开篇前 {f.chapters_analysed} 章（全书 {f.chapters_total} 章）"
            if f.scope_kind == "opening"
            else f"读了全书 {f.chapters_analysed} 章"
        )
        lines.append(f"\n【书号 {f.book_id}】《{f.title}》 · {f.primary_genre or '类型未标'} · {scope}")
        for t in f.techniques:
            lines.append(f"  - 技法名「{t.name}」：{t.what_it_is}")
            if t.why_it_works:
                lines.append(f"    为什么有效：{t.why_it_works}")
    body = "\n".join(lines)
    ids = "、".join(str(f.book_id) for f in usable)

    return f"""下面是 {len(usable)} 本书各自的「可复用技法」清单，来自对每本书的拆解。

{body}

请找出这些书**共同**做的事——不是把清单合并，是看出不同说法背后的同一件事。
例如「用一句反常识的话立住人物」和「用粗俗细节打破严肃场合」，说法不同，做的是同一件事：
用一次认知冲突把人物钉在读者脑子里。

硬性要求：

1. 每一条共性必须由至少 {MIN_SUPPORT} 本书支持，并在 instances 里列出是哪几本，
   以及每本书里对应的**技法名原文**。技法名必须逐字来自上面的清单，不要改写。
2. book_id 只能从这些里选：{ids}。不要出现别的书号。
3. 找不到足够的共性就少给几条。**宁可只给两条真的，也不要凑够五条。**
   「都很会写钩子」这种既正确又无用的话不要写——它对任何一组小说都成立。
4. what_they_do 说清楚具体怎么做的，让人看完能照着用；why_it_works 说它为什么起作用。
5. 如果某本书有明显只有它自己在做的事，放进 not_shared——差异和共性一样有参考价值。

只输出 JSON，逐字按这个形状——**键名不要改**：

{{
  "patterns": [
    {{
      "name": "给这条共性起的名字",
      "what_they_do": "具体怎么做的",
      "why_it_works": "为什么起作用",
      "instances": [
        {{"book_id": 1, "technique_name": "清单里的技法名原文",
          "how_this_book_does_it": "这本书是怎么做的"}}
      ]
    }}
  ],
  "not_shared": [
    {{"book_id": 1, "what_only_this_one_does": "只有这本在做的事"}}
  ]
}}"""


def parse_and_verify(raw: Any, facts: list[BookFacts]) -> dict[str, Any]:
    """校验模型的引用。编造的一律丢掉。

    这不是防备模型作恶，是防备一个已知的失败模式：让模型总结一组材料，它会倾向于
    产出通顺、像样、覆盖全面的结论，而覆盖全面往往意味着有几条是补上去的。补上去的那几条
    看起来和真的一样——除非去核对它引用的书里到底有没有那一招。这里就是那个核对。
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {"patterns": [], "not_shared": [], "dropped": [], "parse_failed": True}
    if not isinstance(raw, dict):
        return {"patterns": [], "not_shared": [], "dropped": [], "parse_failed": True}

    by_id = {f.book_id: f for f in facts if f.usable}
    known_techniques = {
        f.book_id: {t.name for t in f.techniques} for f in facts if f.usable
    }

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []

    # 实测模型把顶层键写成 `shared_techniques`。这类改名不影响内容的真假，
    # 而因为一个键名把一份好结果整个丢掉，用户看到的是「归纳失败」——那是误导。
    raw_patterns = raw.get("patterns") or raw.get("shared_techniques") or []
    for pattern in raw_patterns:
        if not isinstance(pattern, dict):
            continue
        name = str(pattern.get("name") or pattern.get("pattern_name") or "").strip()
        good_instances = []
        raw_instances: list[tuple[Any, str, str]] = []
        for inst in pattern.get("instances") or []:
            if not isinstance(inst, dict):
                continue
            how = str(inst.get("how_this_book_does_it") or "").strip()
            # 实测模型会写成 `technique_names: [...]`（复数、数组）。展平成多条——
            # 同一本书的多条仍然只算一本支持，`distinct_books` 已经保证了这一点。
            names = inst.get("technique_names")
            if isinstance(names, list) and names:
                for n in names:
                    raw_instances.append((inst.get("book_id"), str(n or "").strip(), how))
            else:
                raw_instances.append(
                    (inst.get("book_id"), str(inst.get("technique_name") or "").strip(), how)
                )
        for raw_book_id, tech, how in raw_instances:
            try:
                book_id = int(raw_book_id)
            except (TypeError, ValueError):
                continue
            if book_id not in by_id:
                dropped.append({"pattern": name, "reason": f"引用了不在这组里的书号 {book_id}"})
                continue
            if tech and tech not in known_techniques.get(book_id, set()):
                dropped.append(
                    {"pattern": name, "reason": f"《{by_id[book_id].title}》里没有「{tech}」这一招"}
                )
                continue
            good_instances.append(
                {
                    "book_id": book_id,
                    "book_title": by_id[book_id].title,
                    "technique_name": tech,
                    "how_this_book_does_it": how,
                }
            )
        # 同一本书重复引用不算两本支持。
        distinct_books = {i["book_id"] for i in good_instances}
        if len(distinct_books) < MIN_SUPPORT:
            dropped.append(
                {"pattern": name, "reason": f"经核对只剩 {len(distinct_books)} 本书支持，不足 {MIN_SUPPORT} 本"}
            )
            continue
        if not name:
            # 没给名字时用支持它的第一条技法名顶上——内容都在，缺的只是一个标题。
            name = good_instances[0]["technique_name"] or "共同手法"
        kept.append(
            {
                "name": name,
                "what_they_do": str(pattern.get("what_they_do") or "").strip(),
                "why_it_works": str(pattern.get("why_it_works") or "").strip(),
                "book_count": len(distinct_books),
                "instances": good_instances,
            }
        )

    not_shared = []
    for item in raw.get("not_shared") or []:
        if not isinstance(item, dict):
            continue
        try:
            book_id = int(item.get("book_id"))
        except (TypeError, ValueError):
            continue
        if book_id not in by_id:
            continue
        text = str(item.get("what_only_this_one_does") or "").strip()
        if text:
            not_shared.append(
                {"book_id": book_id, "book_title": by_id[book_id].title, "what_only_this_one_does": text}
            )

    # 支持的书多的排前面：一招十本里有八本在用，比两本在用更值得先看。
    kept.sort(key=lambda p: (-p["book_count"], p["name"]))
    return {"patterns": kept, "not_shared": not_shared, "dropped": dropped, "parse_failed": False}
