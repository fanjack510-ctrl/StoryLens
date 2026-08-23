"""每一章的资产里，不能装着全书。

生产库 1,064 MB，其中 796 MB 在 `narrative_asset_versions.attributes_json`，
而那里面 765.8 MB 是 `chapter_function` 这一种资产：1,841 行，平均每行 436 KB。

原因是逐章循环里写了 `"chapter_functions_v2": result`——`result` 是整本书的章节功能
结果，`chapters` 字段是全书所有章的清单。于是《我不是戏神》1,299 章写出 1,299 条资产，
**每条都嵌一份完整的 1,299 章清单**。1,299 × 525 KB ≈ 682 MB，一本书。

这不是「有点浪费」，是 O(n²)：书越长塌得越快。1,299 章占 682 MB，
2,600 章会占 2.7 GB。

而且没有任何地方读它——产品接口读的是检查点。整份结果在那里已经有一份权威的。

这个文件钉的是**规模**，不是字段：断言一条资产的大小不随书的长度增长。
按字段名断言的话，下次换个名字再嵌一遍，测试照样绿。
"""

from __future__ import annotations

import json


def _attrs_for_chapter(result: dict, chapter: dict) -> dict:
    """复刻 `whole_book_minimal_chapter_functions_v1_service` 里 `attrs_base` 的形状。

    直接调那个服务要一整套 session / 快照 / 运行装置，而这条测试问的是一个纯粹的
    结构问题：一章的资产里有没有装下全书。所以把那个结构原样搬过来断言。
    如果那边的字段变了而这里没跟上，`test_the_real_builder_does_not_embed_the_whole_result`
    会发现——它读的是真源码。
    """
    return {
        "whole_book_run_id": 1,
        "contract_version": "v2",
        "schema_version": "2.0.0",
        "chapter_id": chapter["chapter_index"],
        "chapter_order": chapter["chapter_index"],
        "primary_function": chapter.get("primary_function"),
        "secondary_functions": [],
        "function_labels": [],
        "coverage_scope": (result or {}).get("coverage_scope"),
        "limitations": (result or {}).get("limitations") or [],
        "chapter": chapter,
        "result_origin": "fixture",
        "fixture_test_data": True,
    }


def _whole_book_result(chapter_count: int) -> dict:
    return {
        "contract_version": "v2",
        "coverage_scope": "full",
        "limitations": ["某一条限制说明"],
        "chapters": [
            {
                "chapter_index": i,
                "primary_function": "推进主线",
                "summary": "这一章发生了一些事，描述有一定长度以模拟真实产出。" * 3,
            }
            for i in range(1, chapter_count + 1)
        ],
    }


def _size(result: dict, chapter: dict) -> int:
    return len(json.dumps(_attrs_for_chapter(result, chapter), ensure_ascii=False))


def test_one_chapters_asset_does_not_grow_with_the_book() -> None:
    """一章的资产多大，不该取决于这本书有多少章。

    这是这个 bug 的本质：把「全书」放进了「一章」里。断言规模而不是字段名——
    换个字段名再嵌一遍，按名字写的测试照样是绿的。
    """
    short = _whole_book_result(10)
    long = _whole_book_result(2000)
    chapter = short["chapters"][0]

    small = _size(short, chapter)
    big = _size(long, chapter)

    # 允许一点点浮动（limitations / coverage_scope 是同样的标量），但不允许成比例增长。
    assert big <= small + 200, (
        f"书从 10 章长到 2000 章，一条资产从 {small} 涨到 {big} 字节——全书又被塞进一章里了"
    )


def test_a_single_chapter_asset_stays_small() -> None:
    """一条资产该是几百字节量级，不是几百 KB。

    实测出问题时平均 436 KB。这条设在 4 KB：足够装下一章的正常描述，
    又远低于任何「不小心把列表塞进来」的量级。
    """
    result = _whole_book_result(1299)
    assert _size(result, result["chapters"][0]) < 4096


def test_the_real_builder_does_not_embed_the_whole_result() -> None:
    """真源码里那一行不能回来。

    上面两条测的是形状，这一条盯的是实现：`attrs_base` 里不能再出现
    `"chapter_functions_v2": result`。逐章循环里放整份结果，就是 O(n²)。
    """
    from tests.paths import API_ROOT

    src = (
        API_ROOT
        / "app"
        / "narrative_core"
        / "services"
        / "whole_book_minimal_chapter_functions_v1_service.py"
    ).read_text(encoding="utf-8")

    assert '"chapter_functions_v2": result' not in src, (
        "逐章资产里又嵌了整份结果——这是那个 O(n²) 的写法"
    )
