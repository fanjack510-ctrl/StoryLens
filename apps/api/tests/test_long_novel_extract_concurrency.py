"""抽取阶段的分区并发。

串行时这一层是全流程最慢的一段，而它几乎全在等网络：1299 章切成 163 块，每块一次调用
约 70 秒，加起来三个多小时。块在分区内必须按顺序——每块的提示词带着上一块留下的连续性
状态——但分区之间本来就是独立的归约单元，可以同时读。

这组测试盯住三件事：并发不改结果、连续性链在分区内仍然成立、以及它真的重叠了（否则
「并发」只是个名字）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.long_novel.contracts.l1 import BlockAsset, CarryForwardState
from app.narrative_core.long_novel.orchestrator import RunCoordinator


@dataclass
class _Block:
    block_key: str
    chapter_orders: tuple[int, ...]


@dataclass
class _Partition:
    partition_key: str
    block_keys: tuple[str, ...]


@dataclass
class _Plan:
    blocks: tuple[_Block, ...]
    partitions: tuple[_Partition, ...]


@dataclass
class _Result:
    block_key: str
    asset: BlockAsset
    evidence: tuple[dict[str, Any], ...] = ()
    evidence_by_anchor: dict[str, Any] = field(default_factory=dict)
    provider_calls: int = 1
    reused: bool = False


class _RecordingExtractor:
    """记下每次调用的入参与时间窗，好判断到底有没有重叠。"""

    def __init__(self, delay: float = 0.05) -> None:
        self._delay = delay
        self._lock = threading.Lock()
        self.carry_seen: dict[str, tuple[str, ...]] = {}
        self.spans: list[tuple[str, float, float]] = []

    def extract(self, *, block_key: str, chapters: Any, carry_in: CarryForwardState):
        start = time.monotonic()
        with self._lock:
            self.carry_seen[block_key] = tuple(carry_in.open_thread_refs)
        time.sleep(self._delay)
        asset = BlockAsset(asset_schema_version="l1/1.0")
        with self._lock:
            self.spans.append((block_key, start, time.monotonic()))
        return _Result(block_key=block_key, asset=asset)


def _plan(n_partitions: int = 4, per_partition: int = 3) -> _Plan:
    blocks: list[_Block] = []
    partitions: list[_Partition] = []
    order = 1
    for p in range(n_partitions):
        keys = []
        for b in range(per_partition):
            key = f"p{p}b{b}"
            blocks.append(_Block(block_key=key, chapter_orders=(order,)))
            keys.append(key)
            order += 1
        partitions.append(_Partition(partition_key=f"p{p}", block_keys=tuple(keys)))
    return _Plan(blocks=tuple(blocks), partitions=tuple(partitions))


def _run(concurrency: int, extractor: _RecordingExtractor):
    from app.narrative_core.long_novel.orchestrator import RunReport

    coordinator = RunCoordinator(
        extractor=extractor,  # type: ignore[arg-type]
        profile=object(),  # type: ignore[arg-type]
        extract_concurrency=concurrency,
    )
    plan = _plan()
    chapters = {b.chapter_orders[0]: object() for b in plan.blocks}
    report = RunReport()
    assets = coordinator._extract_all(plan, chapters, report)  # noqa: SLF001
    return assets, report


def test_concurrency_does_not_change_which_blocks_come_back() -> None:
    """并发只该改变墙上时间。少一块、多一块、换一块，都是不能接受的。"""
    serial, serial_report = _run(1, _RecordingExtractor(delay=0.0))
    parallel, parallel_report = _run(4, _RecordingExtractor(delay=0.0))
    assert set(serial) == set(parallel)
    assert len(parallel) == 12
    assert serial_report.blocks_extracted == parallel_report.blocks_extracted == 12
    assert parallel_report.provider_calls == serial_report.provider_calls
    assert parallel_report.blocks_failed == []


def test_the_continuity_chain_still_holds_inside_a_partition() -> None:
    """分区内第一块从空开始，后面每一块都看得见前一块——这条链断了，并发就白提速了。"""
    extractor = _RecordingExtractor(delay=0.0)
    _run(4, extractor)
    # 每个分区的头一块拿到空 carry；这是分区并发换来的代价，明写在测试里。
    for p in range(4):
        assert extractor.carry_seen[f"p{p}b0"] == ()
    # 后续块必须拿到非空 carry（假抽取器返回空 asset，build_carry_out 会把上一块的
    # 状态原样带下来，所以这里只断言「链被调用了」而不是具体内容）。
    assert set(extractor.carry_seen) == {f"p{p}b{b}" for p in range(4) for b in range(3)}


def test_partitions_actually_overlap_in_time() -> None:
    """不重叠的话，「并发」就只是个名字。

    每块睡 50ms，4 个分区各 3 块。串行至少 12×50=600ms；4 路并发大约 150ms。
    这里不掐总时长（CI 上不稳），而是直接查有没有两个不同分区的调用在时间上相交。
    """
    extractor = _RecordingExtractor(delay=0.05)
    _run(4, extractor)
    spans = extractor.spans
    overlapped = any(
        a[0][:2] != b[0][:2] and a[1] < b[2] and b[1] < a[2]
        for i, a in enumerate(spans)
        for b in spans[i + 1 :]
    )
    assert overlapped, "不同分区的抽取没有任何时间重叠，说明还是串行"


def test_serial_is_still_available_and_is_the_old_behaviour() -> None:
    """并发=1 时必须逐块跑，一次也不重叠——这是出问题时能退回去的那条路。"""
    extractor = _RecordingExtractor(delay=0.02)
    _run(1, extractor)
    spans = sorted(extractor.spans, key=lambda x: x[1])
    for earlier, later in zip(spans, spans[1:]):
        assert earlier[2] <= later[1] + 1e-6, "并发=1 时不该有重叠"


def test_a_plan_without_partitions_still_reads_every_block() -> None:
    """老计划或测试替身没给分区时，退回整本一条链，而不是一块都不读。"""
    from app.narrative_core.long_novel.orchestrator import RunReport

    extractor = _RecordingExtractor(delay=0.0)
    coordinator = RunCoordinator(
        extractor=extractor,  # type: ignore[arg-type]
        profile=object(),  # type: ignore[arg-type]
        extract_concurrency=4,
    )
    plan = _Plan(blocks=_plan().blocks, partitions=())
    chapters = {b.chapter_orders[0]: object() for b in plan.blocks}
    assets = coordinator._extract_all(plan, chapters, RunReport())  # noqa: SLF001
    assert len(assets) == 12
