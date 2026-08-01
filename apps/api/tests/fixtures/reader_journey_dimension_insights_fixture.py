"""Fixture data for CHG-20260729-001 dimension insights tests."""

from __future__ import annotations

from typing import Any

DIMENSION_INSIGHTS_FIXTURE_SCENES: list[dict[str, Any]] = [
    {
        "scene_id": 1,
        "scene_ordinal": 1,
        "scene_role": "setup",
        "scene_value_summary": "开篇交代人物处境与章节初始疑问。",
        "scores": {
            "reading_momentum": 42,
            "plot_progress": 38,
            "reading_tension": 35,
            "pacing_speed": 45,
            "hook": 55,
            "payoff": 25,
            "emotional_investment": 40,
        },
        "dimension_insights": {
            "overall_reading": "综合阅读贡献偏弱；铺垫段对继续阅读的整体拉动有限。",
            "plot_progression": "剧情推进偏弱；事件变化有限，主要在建立初始认知。",
            "reading_tension": "阅读张力偏弱；悬念尚未充分建立。",
            "emotional_intensity": "情绪强度偏弱；读者尚未被强烈情感牵动。",
            "hook_payoff": "钩子刚提出而回报不足，问题链处于开启阶段。",
            "pacing_speed": "节奏速度中等偏慢；符合铺垫场景的信息铺设需要。",
        },
        "insight_source": "generated",
    },
    {
        "scene_id": 2,
        "scene_ordinal": 2,
        "scene_role": "transition",
        "scene_value_summary": "场景切换与信息过渡。",
        "scores": {
            "reading_momentum": 48,
            "plot_progress": 32,
            "reading_tension": 40,
            "pacing_speed": 78,
            "hook": 35,
            "payoff": 20,
            "emotional_investment": 38,
        },
        "dimension_insights": {
            "overall_reading": "综合阅读贡献有限；过渡段推进快但剧情增量不大。",
            "plot_progression": "剧情推进偏弱；场景切换完成但实质事件变化不多。",
            "reading_tension": "阅读张力中等；危险感尚未明显抬升。",
            "emotional_intensity": "情绪强度偏弱；读者更多在跟随场景位移。",
            "hook_payoff": "钩子延续有限，回报几乎未落地。",
            "pacing_speed": "节奏速度偏快；叙事推进快于信息增量，存在空转风险。",
        },
        "insight_source": "generated",
    },
    {
        "scene_id": 3,
        "scene_ordinal": 3,
        "scene_role": "escalation",
        "scene_value_summary": "冲突抬升，人物做出关键反应。",
        "scores": {
            "reading_momentum": 62,
            "plot_progress": 68,
            "reading_tension": 38,
            "pacing_speed": 58,
            "hook": 60,
            "payoff": 35,
            "emotional_investment": 82,
        },
        "dimension_insights": {
            "overall_reading": "综合阅读贡献中等偏上；情绪投入增强，但悬念压力尚未同步抬升。",
            "plot_progression": "剧情推进偏强；冲突有抬升，目标与状态出现可见变化。",
            "reading_tension": "阅读张力偏弱；尽管冲突升级，等待感仍不高。",
            "emotional_intensity": "情绪强度偏强；读者对人物处境产生较明显的情感反应。",
            "hook_payoff": "钩子持续存在，回报有限，问题链仍在推进中。",
            "pacing_speed": "节奏速度中等；推进与情绪渲染大致平衡。",
        },
        "insight_source": "generated",
    },
    {
        "scene_id": 4,
        "scene_ordinal": 4,
        "scene_role": "reveal",
        "scene_value_summary": "关键信息揭露，部分前文疑问得到回应。",
        "scores": {
            "reading_momentum": 70,
            "plot_progress": 75,
            "reading_tension": 55,
            "pacing_speed": 60,
            "hook": 50,
            "payoff": 58,
            "emotional_investment": 55,
        },
        "dimension_insights": {
            "overall_reading": "综合阅读贡献较好；信息揭露带来阶段性满足。",
            "plot_progression": "剧情推进偏强；关键信息落地，故事状态发生实质变化。",
            "reading_tension": "阅读张力中等；真相揭晓后悬念压力有所释放。",
            "emotional_intensity": "情绪强度中等；揭晓带来冲击但尚未达到情绪峰值。",
            "hook_payoff": "钩子与回报部分呼应，问题链处于部分兑现阶段。",
            "pacing_speed": "节奏速度中等；信息披露与场景反应节奏匹配。",
        },
        "insight_source": "generated",
    },
    {
        "scene_id": 5,
        "scene_ordinal": 5,
        "scene_role": "climax",
        "scene_value_summary": "章节冲突高点，悬念与回报同时抬升。",
        "scores": {
            "reading_momentum": 88,
            "plot_progress": 85,
            "reading_tension": 92,
            "pacing_speed": 82,
            "hook": 75,
            "payoff": 80,
            "emotional_investment": 78,
        },
        "dimension_insights": {
            "overall_reading": "综合阅读贡献偏强；多维度同步抬升，读者继续阅读动力达到峰值。",
            "plot_progression": "剧情推进偏强；核心冲突集中爆发，故事状态剧烈变化。",
            "reading_tension": "阅读张力偏强；等待、危险与不确定性同时拉满。",
            "emotional_intensity": "情绪强度偏强；高潮段情绪反应强烈且持续。",
            "hook_payoff": "钩子与回报同步抬升，问题链在高潮段得到有效回应。",
            "pacing_speed": "节奏速度偏快；动作与信息密集，符合高潮场景预期。",
        },
        "insight_source": "generated",
    },
    {
        "scene_id": 6,
        "scene_ordinal": 6,
        "scene_role": "aftermath",
        "scene_value_summary": "高潮余波消化，读者情绪回落。",
        "scores": {
            "reading_momentum": 52,
            "plot_progress": 40,
            "reading_tension": 42,
            "pacing_speed": 38,
            "hook": 30,
            "payoff": 55,
            "emotional_investment": 48,
        },
        "dimension_insights": {
            "overall_reading": "综合阅读贡献回落；高潮后进入消化段，整体拉动趋于平稳。",
            "plot_progression": "剧情推进偏弱；主要在处理高潮后果，增量事件有限。",
            "reading_tension": "阅读张力偏弱；紧张感释放，读者处于阶段性安全区。",
            "emotional_intensity": "情绪强度中等；余波仍有余温但不再持续加压。",
            "hook_payoff": "部分钩子已回应，仍有问题留给后续章节。",
            "pacing_speed": "节奏速度偏慢；停顿与观察增多，帮助读者消化高潮。",
        },
        "insight_source": "generated",
    },
]

DETERMINISTIC_STATS_FIXTURE: dict[str, Any] = {
    "v2_scene_scores": {
        str(scene["scene_ordinal"]): scene["scores"] for scene in DIMENSION_INSIGHTS_FIXTURE_SCENES
    },
    "v2_dimension_insights": {
        str(scene["scene_ordinal"]): scene["dimension_insights"]
        for scene in DIMENSION_INSIGHTS_FIXTURE_SCENES
    },
    "v2_node_overrides": {
        str(scene["scene_ordinal"]): {
            "scene_role": scene["scene_role"],
            "node_type": "scene",
            "role": "core",
            "include_in_main_curve": True,
        }
        for scene in DIMENSION_INSIGHTS_FIXTURE_SCENES
    },
    "scene_diagnoses": [],
}
