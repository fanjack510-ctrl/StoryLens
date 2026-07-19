# -*- coding: utf-8 -*-
"""Generate Reader Journey Visualization v2.8 visual-regression SVG fixtures (no model calls)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audits" / "single-chapter-pipeline" / "reader-journey-visual-regression-v2.8"


def chart_svg(
    *,
    title: str,
    scene_count: int,
    height: int,
    values: list[float | None],
    view_start: int = 1,
    view_end: int | None = None,
    brush: bool = False,
    inspector: str = "expanded",
) -> str:
    view_end = view_end or scene_count
    width = max(720, scene_count * 48)
    pad_l, pad_r, pad_t, pad_b = 44, 20, 28, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x(o: int) -> float:
        if scene_count <= 1:
            return pad_l + plot_w / 2
        return pad_l + (o - 1) / (scene_count - 1) * plot_w

    def y(v: float) -> float:
        return pad_t + plot_h - (v / 100.0) * plot_h

    phases = [
        (1, 1, max(1, scene_count // 4), "#e8ede9"),
        (2, max(1, scene_count // 4) + 1, max(2, scene_count // 2), "#f0ebe3"),
        (3, max(2, scene_count // 2) + 1, max(3, (3 * scene_count) // 4), "#e6ebf0"),
        (4, max(3, (3 * scene_count) // 4) + 1, scene_count, "#ede8e6"),
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height + (36 if brush else 0)}" '
        f'viewBox="0 0 {width} {height + (36 if brush else 0)}">',
        f'<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="16" y="18" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#222">{title}</text>',
        f'<text x="16" y="36" font-family="Microsoft YaHei, sans-serif" font-size="11" fill="#666">'
        f"Scenes={scene_count} height={height}px Y=0—100 inspector={inspector} view={view_start}-{view_end}</text>",
    ]

    for _, s, e, color in phases:
        x1 = x(s) - 8
        x2 = x(e) + 8
        parts.append(
            f'<rect x="{x1:.1f}" y="{pad_t}" width="{max(x2 - x1, 4):.1f}" height="{plot_h}" '
            f'fill="{color}" opacity="0.18"/>'
        )

    # risk band mid chapter
    rs = max(1, int(scene_count * 0.4))
    re = max(rs + 1, int(scene_count * 0.55))
    parts.append(
        f'<rect x="{x(rs) - 6:.1f}" y="{pad_t}" width="{max(x(re) - x(rs) + 12, 4):.1f}" '
        f'height="{plot_h}" fill="#f3ddd8" opacity="0.28"/>'
    )

    for tick in (0, 25, 50, 75, 100):
        yy = y(tick)
        parts.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" '
            f'stroke="#ddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 6}" y="{yy + 3:.1f}" text-anchor="end" '
            f'font-family="sans-serif" font-size="10" fill="#666">{tick}</text>'
        )

    # path with breaks
    segment: list[str] = []
    path_bits: list[str] = []
    for i, val in enumerate(values):
        ordinal = i + 1
        if val is None:
            if segment:
                path_bits.append(" ".join(segment))
                segment = []
            continue
        cmd = "M" if not segment else "L"
        segment.append(f"{cmd} {x(ordinal):.1f} {y(val):.1f}")
    if segment:
        path_bits.append(" ".join(segment))
    for d in path_bits:
        parts.append(f'<path d="{d}" fill="none" stroke="#2f6f5e" stroke-width="2.25"/>')

    for i, val in enumerate(values):
        ordinal = i + 1
        if val is None:
            continue
        parts.append(
            f'<circle cx="{x(ordinal):.1f}" cy="{y(val):.1f}" r="5" fill="#fff" '
            f'stroke="#2f6f5e" stroke-width="1.5"/>'
        )

    if brush:
        by = height + 6
        parts.append(
            f'<rect x="{pad_l}" y="{by}" width="{plot_w}" height="22" fill="#f4f4f4" stroke="#ccc"/>'
        )
        bx1 = pad_l + (view_start - 1) / max(scene_count - 1, 1) * plot_w
        bx2 = pad_l + (view_end - 1) / max(scene_count - 1, 1) * plot_w
        parts.append(
            f'<rect x="{bx1:.1f}" y="{by}" width="{max(bx2 - bx1, 8):.1f}" height="22" '
            f'fill="#2f6f5e" opacity="0.35"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        (
            "01-13-scene-standard-full-curve.svg",
            dict(
                title="13 Scene 标准高度完整曲线",
                scene_count=13,
                height=360,
                values=[0, 35, 42, 28, 55, 70, 48, 22, 60, 85, None, 40, 100],
            ),
        ),
        (
            "02-13-scene-expanded-height.svg",
            dict(
                title="13 Scene 展开高度",
                scene_count=13,
                height=520,
                values=[0, 35, 42, 28, 55, 70, 48, 22, 60, 85, None, 40, 100],
            ),
        ),
        (
            "03-30-scene-horizontal-zoom.svg",
            dict(
                title="30 Scene 横向缩放",
                scene_count=30,
                height=360,
                values=[20 + (i * 7) % 70 for i in range(30)],
                view_start=8,
                view_end=18,
            ),
        ),
        (
            "04-60-scene-brush-selection.svg",
            dict(
                title="60 Scene 区间选择",
                scene_count=60,
                height=360,
                values=[15 + (i * 5) % 80 for i in range(60)],
                view_start=20,
                view_end=35,
                brush=True,
            ),
        ),
        (
            "05-inspector-collapsed.svg",
            dict(
                title="Inspector 收起",
                scene_count=13,
                height=360,
                values=[0, 35, 42, 28, 55, 70, 48, 22, 60, 85, None, 40, 100],
                inspector="collapsed",
            ),
        ),
        (
            "06-inspector-expanded.svg",
            dict(
                title="Inspector 展开",
                scene_count=13,
                height=360,
                values=[0, 35, 42, 28, 55, 70, 48, 22, 60, 85, None, 40, 100],
                inspector="expanded",
            ),
        ),
        (
            "07-boundary-0-100.svg",
            dict(
                title="0—100 边界值",
                scene_count=5,
                height=360,
                values=[0, 25, 50, 75, 100],
            ),
        ),
        (
            "08-full-png-export.svg",
            dict(
                title="完整旅程 PNG 导出（独立于视口）",
                scene_count=13,
                height=360,
                values=[0, 35, 42, 28, 55, 70, 48, 22, 60, 85, None, 40, 100],
            ),
        ),
    ]

    manifest = {
        "version": "2.8",
        "generator": "scripts/generate_reader_journey_visual_regression_v2_8.py",
        "note": "Deterministic SVG fixtures; no real model / DB mutation",
        "files": [],
    }
    for name, kwargs in cases:
        path = OUT / name
        path.write_text(chart_svg(**kwargs), encoding="utf-8")
        # Also write a .png sibling marker pointing to SVG (PNG raster optional offline).
        png_note = OUT / name.replace(".svg", ".png.md")
        png_note.write_text(
            f"Visual regression reference for {name}\n"
            f"Canonical SVG: {name}\n"
            f"Rasterize locally if needed; gate uses SVG geometry invariants.\n",
            encoding="utf-8",
        )
        manifest["files"].append(name)

    (OUT / "manifest.json").write_text(
        __import__("json").dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cases)} fixtures to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
