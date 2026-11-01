"""Render the ReproLab insignia: a 512x512 PNG drawn from primitives.

The mark is a replication plate. The outer tick ring is the 250 basis point
decision grid the contract quantizes every audited score onto. The amber curve
is the study baseline, the green curve is the independent replication, and the
two converge on the cyan crosshair, which is the exact-replication band. The
stacked bars at the lower left are reserved custody layers (endowment escrow,
replication bonds, pending refunds).

Everything is generated from scratch with Pillow at four times the target size
and downsampled with a Lanczos filter, so the delivered file is crisp at 512.
The render is fully deterministic: no randomness, no network, no font files.

Usage:
    python scripts/render_reprolab_insignia.py
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

SS = 4  # supersample factor
SIZE = 512 * SS
GRID_TICKS = 40  # 10000 bps / 250 bps
MAJOR_EVERY = 4  # 1000 bps

INK = (11, 19, 43)  # #0B132B
SLATE = (28, 37, 65)  # #1C2541
CYAN = (6, 182, 212)  # #06B6D4
GREEN = (16, 185, 129)  # #10B981
AMBER = (245, 158, 11)  # #F59E0B
RIM = (148, 163, 184)

CX = SIZE // 2
CY = SIZE // 2


def _p(angle: float, radius: float) -> tuple[float, float]:
    return CX + radius * math.cos(angle), CY + radius * math.sin(angle)


def ring(draw: ImageDraw.ImageDraw) -> None:
    """Tick ring: one mark per 250 bps grid step, major marks at 1000 bps."""
    outer = SIZE * 0.455
    for index in range(GRID_TICKS):
        angle = -math.pi / 2 + index * 2 * math.pi / GRID_TICKS
        major = index % MAJOR_EVERY == 0
        inner = outer - (SIZE * 0.055 if major else SIZE * 0.028)
        colour = CYAN if major else SLATE
        width = int(SIZE * 0.011) if major else int(SIZE * 0.006)
        draw.line([_p(angle, inner), _p(angle, outer)], fill=colour, width=width)
    draw.ellipse(
        [CX - outer, CY - outer, CX + outer, CY + outer],
        outline=SLATE,
        width=int(SIZE * 0.006),
    )
    rim = SIZE * 0.385
    draw.ellipse(
        [CX - rim, CY - rim, CX + rim, CY + rim],
        outline=(23, 34, 60),
        width=int(SIZE * 0.005),
    )


def curves(draw: ImageDraw.ImageDraw) -> None:
    """Baseline and replication curves converging on the crosshair."""
    left = CX - SIZE * 0.30
    right = CX + SIZE * 0.24
    steps = 260
    base_top = CY - SIZE * 0.155
    for series, colour, weight, wobble in (
        ("baseline", AMBER, int(SIZE * 0.019), 1.0),
        ("replication", GREEN, int(SIZE * 0.019), -1.0),
    ):
        points = []
        for index in range(steps + 1):
            t = index / steps
            x = left + (right - left) * t
            # Both series approach the same settled value as t goes to 1.
            settle = base_top + SIZE * 0.055 * t
            spread = SIZE * 0.128 * (1.0 - t) ** 1.7
            tremor = math.sin(t * 11.0 + (0.0 if wobble > 0 else 2.2)) * spread * 0.34
            y = settle - wobble * (spread * 0.5 + tremor)
            points.append((x, y))
        draw.line(points, fill=colour, width=weight, joint="curve")
        # Node dots at every grid crossing keep the plate reading as data.
        for index in range(0, steps + 1, steps // 8):
            x, y = points[index]
            dot = SIZE * 0.008
            draw.ellipse([x - dot, y - dot, x + dot, y + dot], fill=colour)


def crosshair(draw: ImageDraw.ImageDraw) -> None:
    """The exact-replication band where both series agree."""
    x, y = CX + SIZE * 0.24, CY - SIZE * 0.10
    arm = SIZE * 0.052
    draw.line([(x - arm, y), (x + arm, y)], fill=CYAN, width=int(SIZE * 0.010))
    draw.line([(x, y - arm), (x, y + arm)], fill=CYAN, width=int(SIZE * 0.010))
    halo = SIZE * 0.030
    draw.ellipse([x - halo, y - halo, x + halo, y + halo], outline=CYAN, width=int(SIZE * 0.008))
    core = SIZE * 0.011
    draw.ellipse([x - core, y - core, x + core, y + core], fill=CYAN)


def custody_stack(draw: ImageDraw.ImageDraw) -> None:
    """Three reserved custody layers, widest at the bottom."""
    left = CX - SIZE * 0.300
    bar_h = SIZE * 0.032
    gap = SIZE * 0.021
    top = CY + SIZE * 0.150
    widths = [SIZE * 0.150, SIZE * 0.196, SIZE * 0.242]
    for level, width in enumerate(widths):
        y0 = top + level * (bar_h + gap)
        x0 = left + (widths[-1] - width) / 2
        draw.rounded_rectangle(
            [x0, y0, x0 + width, y0 + bar_h],
            radius=bar_h * 0.45,
            fill=SLATE,
            outline=(45, 61, 100),
            width=int(SIZE * 0.005),
        )
        # Cyan fill ratio suggests how much of the layer is reserved.
        fill = width * (0.82 - 0.10 * level)
        draw.rounded_rectangle(
            [x0, y0, x0 + fill, y0 + bar_h],
            radius=bar_h * 0.45,
            fill=(9, 61, 84),
        )
    bond = SIZE * 0.016
    by = top + 3 * (bar_h + gap) + bond
    draw.ellipse([left + bond, by - bond, left + bond * 3, by + bond], fill=AMBER)
    draw.line(
        [(left + bond * 3.6, by), (left + widths[-1] - bond, by)],
        fill=(71, 85, 122),
        width=int(SIZE * 0.005),
    )


def render() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), INK)
    draw = ImageDraw.Draw(img)
    # Plate: rounded square with a slightly lighter inner field.
    pad = SIZE * 0.020
    draw.rounded_rectangle(
        [pad, pad, SIZE - pad, SIZE - pad],
        radius=SIZE * 0.115,
        fill=(9, 16, 37),
        outline=(35, 47, 80),
        width=int(SIZE * 0.012),
    )
    inner = SIZE * 0.085
    draw.rounded_rectangle(
        [inner, inner, SIZE - inner, SIZE - inner],
        radius=SIZE * 0.095,
        outline=SLATE,
        width=int(SIZE * 0.005),
    )
    ring(draw)
    curves(draw)
    custody_stack(draw)
    crosshair(draw)
    # Corner registration marks, an archival plate convention.
    mark = SIZE * 0.030
    inset = SIZE * 0.062
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = CX + sx * (SIZE / 2 - inset)
            y = CY + sy * (SIZE / 2 - inset)
            draw.line([(x - mark * sx, y), (x, y)], fill=RIM, width=int(SIZE * 0.005))
            draw.line([(x, y - mark * sy), (x, y)], fill=RIM, width=int(SIZE * 0.005))
    return img.resize((512, 512), Image.LANCZOS)


def main() -> None:
    img = render()
    targets = ["frontend/public/logo.png", "docs/logo.png"]
    for target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        img.save(target, format="PNG", optimize=True)
        size = os.path.getsize(target)
        print(f"{target}: {img.size[0]}x{img.size[1]} png, {size} bytes ({size / 1024:.1f} KB)")
        if size > 500 * 1024:
            raise SystemExit(f"{target} exceeds the 500 KB limit")


if __name__ == "__main__":
    main()
