import argparse
import json
import statistics
from pathlib import Path


def boundary_metrics(expected: list[set[str]], predicted: list[set[str]]) -> dict[str, float | int]:
    tp = sum(len(left & right) for left, right in zip(expected, predicted, strict=True))
    fp = sum(len(right - left) for left, right in zip(expected, predicted, strict=True))
    fn = sum(len(left - right) for left, right in zip(expected, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="local_qwen14")
    parser.add_argument("--prompt-version", default="v2")
    parser.add_argument("--results", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("data/runtime/local_llama/calibration.json")
    )
    args = parser.parse_args()
    if not args.results:
        print("A real results JSON file is required; calibration is never fabricated.")
        return 3
    rows = json.loads(args.results.read_text(encoding="utf-8"))
    metrics = boundary_metrics(
        [set(row["expected_boundaries"]) for row in rows],
        [set(row["predicted_boundaries"]) for row in rows],
    )
    latencies = [float(row["latency_ms"]) for row in rows]
    report = {
        "provider": args.provider,
        "prompt_version": args.prompt_version,
        "sample_count": len(rows),
        **metrics,
        "no_boundary_accuracy": statistics.mean(
            not row["predicted_boundaries"] for row in rows if not row["expected_boundaries"]
        ),
        "first_json_valid_rate": statistics.mean(row["first_json_valid"] for row in rows),
        "final_json_valid_rate": statistics.mean(row["final_json_valid"] for row in rows),
        "first_schema_valid_rate": statistics.mean(row["first_schema_valid"] for row in rows),
        "final_schema_valid_rate": statistics.mean(row["final_schema_valid"] for row in rows),
        "average_invocations": statistics.mean(row["invocation_count"] for row in rows),
        "repair_rate": statistics.mean(row["repair_count"] > 0 for row in rows),
        "illegal_evidence_count": sum(row["illegal_evidence_count"] for row in rows),
        "scene_coverage_rate": statistics.mean(row["scene_coverage_rate"] for row in rows),
        "prompt_injection_protection_rate": statistics.mean(
            row["prompt_injection_safe"] for row in rows
        ),
        "average_latency_ms": statistics.mean(latencies),
        "p50_latency_ms": percentile(latencies, 0.5),
        "p95_latency_ms": percentile(latencies, 0.95),
        "peak_temperature_c": max(row["peak_temperature_c"] for row in rows),
        "peak_vram_mb": max(row["peak_vram_mb"] for row in rows),
        "structured_output_mode": rows[0]["structured_output_mode"],
        "thinking_enabled": any(row["thinking_enabled"] for row in rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
