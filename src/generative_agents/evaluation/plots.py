"""Small dependency-free SVG charts for the Markdown reports."""

from __future__ import annotations

import math
from html import escape

INK = "#16211B"
MUTED = "#5B6B61"
COLORS = ["#2353AC", "#B4461C", "#6B3E9B", "#1E6E62", "#6E5A1E"]


def bar_chart(title: str, groups: list[str], series: dict[str, list[float | None]], *, unit: str = "", width: int = 560, height: int = 260) -> str:
    pad_l, pad_b, pad_t = 48, 52, 36
    plot_w, plot_h = width - pad_l - 16, height - pad_t - pad_b
    vals = [v for s in series.values() for v in s if v is not None]
    top = max(vals + [1.0])
    n_s = max(1, len(series))
    gw = plot_w / max(1, len(groups))
    bw = gw * 0.7 / n_s
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="IBM Plex Mono, monospace" font-size="11">']
    out.append(f'<text x="{pad_l}" y="20" fill="{INK}" font-size="13">{escape(title)}</text>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" stroke="{MUTED}"/>')
    for gi, g in enumerate(groups):
        for si, (name, vs) in enumerate(series.items()):
            v = vs[gi]
            x = pad_l + gi * gw + gw * 0.15 + si * bw
            if v is None:
                out.append(f'<text x="{x + bw / 2:.1f}" y="{pad_t + plot_h - 4}" text-anchor="middle" fill="{MUTED}">n/a</text>')
                continue
            h = plot_h * (v / top)
            out.append(
                f'<rect x="{x:.1f}" y="{pad_t + plot_h - h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{COLORS[si % len(COLORS)]}"><title>{escape(name)}: {v:g}{unit}</title></rect>'
            )
            out.append(f'<text x="{x + bw / 2:.1f}" y="{pad_t + plot_h - h - 4:.1f}" text-anchor="middle" fill="{INK}">{v:g}</text>')
        out.append(f'<text x="{pad_l + gi * gw + gw / 2:.1f}" y="{pad_t + plot_h + 16}" text-anchor="middle" fill="{INK}">{escape(g)}</text>')
    for si, name in enumerate(series):
        out.append(f'<rect x="{pad_l + si * 150}" y="{height - 18}" width="10" height="10" fill="{COLORS[si % len(COLORS)]}"/>')
        out.append(f'<text x="{pad_l + si * 150 + 14}" y="{height - 9}" fill="{INK}">{escape(name)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def network(title: str, nodes: list[str], edges: list[tuple[str, str]], *, directed: bool = False, highlight: str | None = None, size: int = 420) -> str:
    cx = cy = size / 2
    r = size / 2 - 70
    pos = {
        n: (cx + r * math.cos(2 * math.pi * i / max(1, len(nodes)) - math.pi / 2), cy + 10 + r * math.sin(2 * math.pi * i / max(1, len(nodes)) - math.pi / 2))
        for i, n in enumerate(nodes)
    }
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size + 20}" font-family="IBM Plex Mono, monospace" font-size="10">']
    out.append(
        '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#2353AC"/></marker></defs>'
    )
    out.append(f'<text x="12" y="18" fill="{INK}" font-size="13">{escape(title)}</text>')
    for a, b in edges:
        if a not in pos or b not in pos:
            continue
        (x1, y1), (x2, y2) = pos[a], pos[b]
        if directed:
            d = math.hypot(x2 - x1, y2 - y1) or 1
            x2, y2 = x2 - (x2 - x1) * 9 / d, y2 - (y2 - y1) * 9 / d
        marker = ' marker-end="url(#arr)"' if directed else ""
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#2353AC" stroke-width="1.4" opacity="0.8"{marker}/>')
    for n, (x, y) in pos.items():
        fill = "#B4461C" if n == highlight else "#FBFCFA"
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{fill}" stroke="{INK}"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 19:.1f}" text-anchor="middle" fill="{INK}">{escape(n)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def strip_chart(title: str, groups: dict[str, list[tuple[str, float]]], *, lo: float = 0.0, hi: float = 1.0, width: int = 420, height: int = 240) -> str:
    """One dot per run for each group, with the group mean as a short bar.

    The axis is fixed (``lo``..``hi``, widened only if a value falls outside) so that a
    difference between a handful of runs is not magnified by auto-scaling. Equal values are
    spread sideways instead of being drawn on top of each other.
    """

    vals = [v for pts in groups.values() for _, v in pts]
    lo, hi = min([lo, *vals]), max([hi, *vals])
    span = (hi - lo) or 1.0
    pad_l, pad_b, pad_t = 48, 30, 36
    plot_w, plot_h = width - pad_l - 16, height - pad_t - pad_b
    gw = plot_w / max(1, len(groups))

    def y(v: float) -> float:
        return pad_t + plot_h - plot_h * (v - lo) / span

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="IBM Plex Mono, monospace" font-size="11">']
    out.append(f'<text x="{pad_l}" y="20" fill="{INK}" font-size="13">{escape(title)}</text>')
    for tick in (lo, lo + span / 2, hi):
        out.append(f'<line x1="{pad_l}" y1="{y(tick):.1f}" x2="{pad_l + plot_w}" y2="{y(tick):.1f}" stroke="{MUTED}" stroke-opacity="0.35"/>')
        out.append(f'<text x="{pad_l - 6}" y="{y(tick) + 4:.1f}" text-anchor="end" fill="{MUTED}">{tick:g}</text>')
    for gi, (name, pts) in enumerate(groups.items()):
        cx = pad_l + gi * gw + gw / 2
        color = COLORS[gi % len(COLORS)]
        seen: dict[float, int] = {}
        for label, v in pts:
            k = seen.get(v, 0)
            seen[v] = k + 1
            dx = ((k + 1) // 2) * 9 * (1 if k % 2 else -1)
            out.append(f'<circle cx="{cx + dx:.1f}" cy="{y(v):.1f}" r="4.5" fill="{color}" fill-opacity="0.8"><title>{escape(label)}: {v:g}</title></circle>')
        if pts:
            mean = sum(v for _, v in pts) / len(pts)
            out.append(f'<line x1="{cx - gw * 0.3:.1f}" y1="{y(mean):.1f}" x2="{cx + gw * 0.3:.1f}" y2="{y(mean):.1f}" stroke="{INK}" stroke-width="2"/>')
            out.append(f'<text x="{cx + gw * 0.3 + 4:.1f}" y="{y(mean) + 4:.1f}" fill="{INK}">{mean:.2f}</text>')
        out.append(f'<text x="{cx:.1f}" y="{pad_t + plot_h + 18}" text-anchor="middle" fill="{INK}">{escape(name)} (n={len(pts)})</text>')
    out.append("</svg>")
    return "\n".join(out)
