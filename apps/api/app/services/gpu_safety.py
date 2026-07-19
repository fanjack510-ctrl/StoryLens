from dataclasses import dataclass


@dataclass(frozen=True)
class GpuMetrics:
    temperature_c: float
    utilization_percent: float
    vram_mb: float
    power_w: float | None


def parse_nvidia_smi_line(line: str) -> GpuMetrics:
    values = [value.strip() for value in line.split(",")]
    if len(values) != 4:
        raise ValueError("Expected four nvidia-smi metrics")
    power = None if values[3] in {"", "N/A", "[N/A]"} else float(values[3])
    return GpuMetrics(float(values[0]), float(values[1]), float(values[2]), power)


def safety_stop_reason(
    metrics: GpuMetrics, *, max_temperature_c: float, max_vram_mb: float
) -> str | None:
    if metrics.temperature_c >= max_temperature_c:
        return "temperature_threshold"
    if metrics.vram_mb >= max_vram_mb:
        return "vram_threshold"
    return None
