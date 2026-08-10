from app.narrative_core.whole_book_v2.pipeline import (
    ChapterMeta,
    ProviderBudget,
    plan_windows,
    build_token_plan,
    build_cost_plan,
)
from app.narrative_core.services.whole_book_cost_estimate_service import (
    _estimate_provider_call_breakdown,
    _estimate_window_count,
)
from app.services.provider_pricing import (
    estimate_tokens_heuristic,
    estimate_pre_run_cost_cny,
    DEEPSEEK_MODEL_FLASH,
)
import math
import json

chapter_count = 542
character_count = 2_901_455
proxy = ("汉" * min(character_count, 50_000))
sample = estimate_tokens_heuristic(proxy)
total_input = int(math.ceil(sample * (character_count / len(proxy))))
windows_min = _estimate_window_count(total_input)
bd = _estimate_provider_call_breakdown(window_count=windows_min, chapter_count=chapter_count)
window_input = windows_min * 18000
synthesis_input = 4000 + min(8000, windows_min * 200)
est_in = window_input + synthesis_input
est_out = windows_min * 3000 + 6000
cmin, cmax, _ = estimate_pre_run_cost_cny(
    DEEPSEEK_MODEL_FLASH,
    estimated_input_tokens=est_in,
    estimated_output_tokens_min=int(round(est_out * 0.85)),
    estimated_output_tokens_max=int(round(est_out * 1.25)),
)

per = max(1, character_count // chapter_count)
rem = character_count - per * chapter_count
chapters = []
for i in range(chapter_count):
    size = per + (rem if i == chapter_count - 1 else 0)
    chapters.append(
        ChapterMeta(
            chapter_id=i + 1,
            chapter_index=i + 1,
            title=f"c{i + 1}",
            text="汉" * size,
            snapshot_id=1,
            revision_hash="r",
        )
    )
budget = ProviderBudget(provider="deepseek", model=DEEPSEEK_MODEL_FLASH)
wins = plan_windows(chapters, book_id=77, budget=budget)
token = build_token_plan(wins, budget=budget)
cost = build_cost_plan(token, budget)

out = {
    "free_minimal": {
        "window_count": windows_min,
        "breakdown": bd,
        "estimated_input_tokens": est_in,
        "estimated_output_tokens": est_out,
        "estimated_cost_min": cmin,
        "estimated_cost_max": cmax,
        "total_book_input_tokens_heuristic": total_input,
    },
    "hierarchical_v2": {
        "window_count": token.window_count,
        "extract_calls": token.extract_calls,
        "consolidation_calls": token.consolidation_calls,
        "final_synthesis_calls": token.final_synthesis_calls,
        "repair_reserve_calls": token.repair_reserve_calls,
        "estimated_total_calls": token.estimated_total_calls,
        "estimated_input_tokens": token.estimated_input_tokens,
        "estimated_output_tokens": token.estimated_output_tokens,
        "estimated_cost_low": cost.estimated_cost_low,
        "estimated_cost_high": cost.estimated_cost_high,
        "context_safe": token.context_safe,
        "max_single_request_total_tokens": token.max_single_request_total_tokens,
    },
}
print(json.dumps(out, ensure_ascii=False, indent=2))
