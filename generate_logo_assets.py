"""Generate procedural logo assets without external dependencies.

The GUI renders its logo procedurally via :mod:`PySide6`, but regenerating the
PNG/ICO assets for distribution or social media previously required a Qt
environment. This standalone script reproduces the same artwork using pure
Python drawing primitives so that the assets can be rebuilt inside headless
CI containers as well.

Running the module will overwrite the files inside :mod:`images/` with fresh
renders of multiple resolutions plus an ICO bundle.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Callable, Iterable, Tuple

Color = Tuple[int, int, int, int]
Point = Tuple[float, float]
Rect = Tuple[float, float, float, float]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _hex_to_rgba(value: str, alpha: int = 255) -> Color:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected 6-digit hex colour, got {value!r}")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return (r, g, b, alpha)


def _lerp_color(a: Color, b: Color, t: float) -> Color:
    t = _clamp(t, 0.0, 1.0)
    return tuple(
        int(round(a[idx] + (b[idx] - a[idx]) * t)) for idx in range(3)
    ) + (int(round(a[3] + (b[3] - a[3]) * t)),)


def _scale_color(color: Color, factor: float, *, alpha: int | None = None) -> Color:
    scaled = tuple(
        int(round(_clamp(component * factor, 0.0, 255.0))) for component in color[:3]
    )
    if alpha is None:
        alpha = color[3]
    return scaled + (alpha,)


def _linear_gradient(
    start: Point, end: Point, colour_a: Color, colour_b: Color
) -> Callable[[float, float], Color]:
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return lambda _x, _y: colour_a

    def _colour(x: float, y: float) -> Color:
        t = ((x - sx) * dx + (y - sy) * dy) / denom
        return _lerp_color(colour_a, colour_b, t)

    return _colour


def _rounded_rect_contains(
    x: float,
    y: float,
    rect: Rect,
    radius: float,
) -> bool:
    left, top, right, bottom = rect
    if right <= left or bottom <= top:
        return False

    radius = max(0.0, min(radius, (right - left) / 2.0, (bottom - top) / 2.0))
    if radius == 0:
        return left <= x <= right and top <= y <= bottom

    inner_left = left + radius
    inner_right = right - radius
    inner_top = top + radius
    inner_bottom = bottom - radius

    if inner_left <= x <= inner_right and inner_top <= y <= inner_bottom:
        return True

    dx = 0.0
    dy = 0.0
    if x < inner_left:
        dx = inner_left - x
    elif x > inner_right:
        dx = x - inner_right
    if y < inner_top:
        dy = inner_top - y
    elif y > inner_bottom:
        dy = y - inner_bottom

    return dx * dx + dy * dy <= radius * radius


def _point_in_triangle(p: Point, a: Point, b: Point, c: Point) -> bool:
    px, py = p
    ax, ay = a
    bx, by = b
    cx, cy = c

    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay

    dot00 = v0x * v0x + v0y * v0y
    dot01 = v0x * v1x + v0y * v1y
    dot02 = v0x * v2x + v0y * v2y
    dot11 = v1x * v1x + v1y * v1y
    dot12 = v1x * v2x + v1y * v2y

    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) <= 1e-9:
        return False

    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return u >= 0 and v >= 0 and (u + v) <= 1


def _distance_to_segment(p: Point, a: Point, b: Point) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    if abs(vx) <= 1e-9 and abs(vy) <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)
    t = _clamp(t, 0.0, 1.0)
    cx = ax + vx * t
    cy = ay + vy * t
    return math.hypot(px - cx, py - cy)


class _Image:
    def __init__(self, size: int) -> None:
        self.width = size
        self.height = size
        self._rows = [bytearray([0, 0, 0, 0] * size) for _ in range(size)]

    def blend_pixel(self, x: int, y: int, color: Color) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        sr, sg, sb, sa = color
        if sa <= 0:
            return
        row = self._rows[y]
        idx = x * 4
        dr, dg, db, da = row[idx : idx + 4]
        if sa >= 255 and da == 0:
            row[idx : idx + 4] = bytes(color)
            return

        sa_f = sa / 255.0
        da_f = da / 255.0
        out_a = sa_f + da_f * (1.0 - sa_f)
        if out_a <= 0:
            row[idx : idx + 4] = b"\x00\x00\x00\x00"
            return

        out_r = (sr * sa_f + dr * da_f * (1.0 - sa_f)) / out_a
        out_g = (sg * sa_f + dg * da_f * (1.0 - sa_f)) / out_a
        out_b = (sb * sa_f + db * da_f * (1.0 - sa_f)) / out_a

        row[idx] = int(round(_clamp(out_r, 0.0, 255.0)))
        row[idx + 1] = int(round(_clamp(out_g, 0.0, 255.0)))
        row[idx + 2] = int(round(_clamp(out_b, 0.0, 255.0)))
        row[idx + 3] = int(round(_clamp(out_a * 255.0, 0.0, 255.0)))

    def paint_rounded_rect(
        self,
        rect: Rect,
        radius: float,
        colour_fn: Callable[[float, float], Color],
    ) -> None:
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            return
        radius = max(0.0, min(radius, (right - left) / 2.0, (bottom - top) / 2.0))
        min_x = max(int(math.floor(left)), 0)
        max_x = min(int(math.ceil(right)), self.width)
        min_y = max(int(math.floor(top)), 0)
        max_y = min(int(math.ceil(bottom)), self.height)

        for y in range(min_y, max_y):
            yc = y + 0.5
            for x in range(min_x, max_x):
                xc = x + 0.5
                if _rounded_rect_contains(xc, yc, rect, radius):
                    self.blend_pixel(x, y, colour_fn(xc, yc))

    def paint_triangle(
        self,
        a: Point,
        b: Point,
        c: Point,
        colour_fn: Callable[[float, float], Color],
    ) -> None:
        min_x = max(int(math.floor(min(a[0], b[0], c[0]))), 0)
        max_x = min(int(math.ceil(max(a[0], b[0], c[0]))), self.width)
        min_y = max(int(math.floor(min(a[1], b[1], c[1]))), 0)
        max_y = min(int(math.ceil(max(a[1], b[1], c[1]))), self.height)

        for y in range(min_y, max_y):
            yc = y + 0.5
            for x in range(min_x, max_x):
                xc = x + 0.5
                if _point_in_triangle((xc, yc), a, b, c):
                    self.blend_pixel(x, y, colour_fn(xc, yc))

    def paint_line(self, a: Point, b: Point, thickness: float, color: Color) -> None:
        if thickness <= 0:
            return
        half = thickness / 2.0
        min_x = max(int(math.floor(min(a[0], b[0]) - half)), 0)
        max_x = min(int(math.ceil(max(a[0], b[0]) + half)), self.width)
        min_y = max(int(math.floor(min(a[1], b[1]) - half)), 0)
        max_y = min(int(math.ceil(max(a[1], b[1]) + half)), self.height)

        for y in range(min_y, max_y):
            yc = y + 0.5
            for x in range(min_x, max_x):
                xc = x + 0.5
                if _distance_to_segment((xc, yc), a, b) <= half:
                    self.blend_pixel(x, y, color)

    def to_png_bytes(self) -> bytes:
        raw = bytearray()
        for row in self._rows:
            raw.append(0)
            raw.extend(row)
        compressed = zlib.compress(bytes(raw), level=9)

        def chunk(tag: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(tag + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

        header = chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0),
        )
        idat = chunk(b"IDAT", compressed)
        end = chunk(b"IEND", b"")
        return b"\x89PNG\r\n\x1a\n" + header + idat + end

    def save_png(self, path: Path) -> None:
        path.write_bytes(self.to_png_bytes())


def _render_logo(size: int) -> _Image:
    img = _Image(size)
    padding = size * 0.08
    rect: Rect = (padding, padding, size - padding, size - padding)
    radius = size * 0.24

    shadow_offset_x = size * 0.04
    shadow_offset_y = size * 0.05
    shadow_rect: Rect = (
        rect[0] + shadow_offset_x,
        rect[1] + shadow_offset_y,
        rect[2] + shadow_offset_x,
        rect[3] + shadow_offset_y,
    )
    img.paint_rounded_rect(shadow_rect, radius * 1.05, lambda _x, _y: _hex_to_rgba("#000000", 55))

    img.paint_rounded_rect(rect, radius, lambda _x, _y: _hex_to_rgba("#08172c"))

    border = max(size * 0.045, 1.0)
    inner_rect: Rect = (
        rect[0] + border,
        rect[1] + border,
        rect[2] - border,
        rect[3] - border,
    )
    inner_radius = max(0.0, radius - border)
    base_gradient = _linear_gradient(
        (inner_rect[0], inner_rect[1]),
        (inner_rect[2], inner_rect[3]),
        _hex_to_rgba("#0b1d36"),
        _hex_to_rgba("#1e4074"),
    )
    img.paint_rounded_rect(inner_rect, inner_radius, base_gradient)

    sheet_rect: Rect = (
        inner_rect[0] + (inner_rect[2] - inner_rect[0]) * 0.16,
        inner_rect[1] + (inner_rect[3] - inner_rect[1]) * 0.16,
        inner_rect[2] - (inner_rect[2] - inner_rect[0]) * 0.16,
        inner_rect[3] - (inner_rect[3] - inner_rect[1]) * 0.16,
    )
    sheet_radius = inner_radius * 0.7
    img.paint_rounded_rect(sheet_rect, sheet_radius, lambda _x, _y: _hex_to_rgba("#1b365f"))

    sheet_border = max((sheet_rect[2] - sheet_rect[0]) * 0.03, 1.0)
    sheet_inner_rect: Rect = (
        sheet_rect[0] + sheet_border,
        sheet_rect[1] + sheet_border,
        sheet_rect[2] - sheet_border,
        sheet_rect[3] - sheet_border,
    )
    sheet_inner_radius = max(0.0, sheet_radius - sheet_border)
    sheet_gradient = _linear_gradient(
        (sheet_inner_rect[0], sheet_inner_rect[1]),
        (sheet_inner_rect[2], sheet_inner_rect[3]),
        _hex_to_rgba("#f9fcff"),
        _hex_to_rgba("#e0e8ff"),
    )
    img.paint_rounded_rect(sheet_inner_rect, sheet_inner_radius, sheet_gradient)

    sheet_inner_width = sheet_inner_rect[2] - sheet_inner_rect[0]
    sheet_inner_height = sheet_inner_rect[3] - sheet_inner_rect[1]

    accent_rect: Rect = (
        sheet_inner_rect[0] + sheet_inner_width * 0.05,
        sheet_inner_rect[1] + sheet_inner_height * 0.12,
        sheet_inner_rect[0] + sheet_inner_width * 0.05 + sheet_inner_width * 0.08,
        sheet_inner_rect[1] + sheet_inner_height * 0.12 + sheet_inner_height * 0.76,
    )
    accent_radius = (accent_rect[3] - accent_rect[1]) / 2.2
    accent_gradient = _linear_gradient(
        (accent_rect[0], accent_rect[1]),
        (accent_rect[2], accent_rect[3]),
        _hex_to_rgba("#4aa8ff"),
        _hex_to_rgba("#2465dd"),
    )
    img.paint_rounded_rect(accent_rect, accent_radius, accent_gradient)

    line_height = sheet_inner_height / 5.2
    vertical_margin = (sheet_inner_height - 3 * line_height) / 4.0
    start_x = accent_rect[2] + sheet_inner_width * 0.06
    end_x = sheet_inner_rect[2] - sheet_inner_width * 0.1

    accents: list[tuple[str, Color]] = [
        ("plus", _hex_to_rgba("#3ddc97")),
        ("minus", _hex_to_rgba("#ff6b6b")),
        ("review", _hex_to_rgba("#4aa8ff")),
    ]

    y = sheet_inner_rect[1] + vertical_margin
    for kind, accent in accents:
        line_rect: Rect = (start_x, y, end_x, y + line_height)
        if line_rect[2] <= line_rect[0]:
            break
        highlight = (accent[0], accent[1], accent[2], 60)
        img.paint_rounded_rect(line_rect, line_height / 2.3, lambda _x, _y, h=highlight: h)

        stroke = _scale_color(accent, 0.82)
        line_thickness = max(line_height * 0.42, size * 0.01)
        core_rect: Rect = (
            line_rect[0] + line_height * 0.55,
            (line_rect[1] + line_rect[3]) / 2.0 - line_thickness / 2.0,
            line_rect[2] - line_height * 0.55,
            (line_rect[1] + line_rect[3]) / 2.0 + line_thickness / 2.0,
        )
        img.paint_rounded_rect(core_rect, line_thickness / 2.0, lambda _x, _y, c=stroke: c)

        centre_y = (line_rect[1] + line_rect[3]) / 2.0
        if kind == "plus":
            mid_x = (core_rect[0] + core_rect[2]) / 2.0
            vertical_rect: Rect = (
                mid_x - line_thickness / 2.0,
                centre_y - line_height * 0.6,
                mid_x + line_thickness / 2.0,
                centre_y + line_height * 0.6,
            )
            img.paint_rounded_rect(
                vertical_rect,
                line_thickness / 2.0,
                lambda _x, _y, c=stroke: c,
            )
        elif kind == "review":
            dots = 4
            spacing = (line_rect[2] - line_rect[0]) / (dots + 1)
            dot_radius = line_thickness * 0.6
            for idx in range(dots):
                cx = line_rect[0] + spacing * (idx + 1)
                dot_rect: Rect = (
                    cx - dot_radius,
                    centre_y - dot_radius,
                    cx + dot_radius,
                    centre_y + dot_radius,
                )
                img.paint_rounded_rect(
                    dot_rect,
                    dot_radius,
                    lambda _x, _y, c=stroke: c,
                )

        y += line_height + vertical_margin

    fold_width = sheet_inner_width * 0.28
    fold_height = sheet_inner_height * 0.28
    fold_rect: Rect = (
        sheet_inner_rect[2] - fold_width,
        sheet_inner_rect[1] + sheet_inner_height * 0.05,
        sheet_inner_rect[2],
        sheet_inner_rect[1] + sheet_inner_height * 0.05 + fold_height,
    )
    p0: Point = (fold_rect[0], fold_rect[1])
    p1: Point = (fold_rect[2], fold_rect[1])
    p2: Point = (fold_rect[2], fold_rect[3])
    fold_gradient = _linear_gradient(p0, p2, _hex_to_rgba("#d1ddff"), _hex_to_rgba("#a8bbff"))
    img.paint_triangle(p0, p1, p2, fold_gradient)

    border_colour = _hex_to_rgba("#1b365f")
    edge_thickness = max(size * 0.01, 1.0)
    img.paint_line(p0, p1, edge_thickness, border_colour)
    img.paint_line(p1, p2, edge_thickness, border_colour)
    img.paint_line(p0, p2, edge_thickness, border_colour)

    return img


def _save_logo_set(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 48, 64, 128, 256, 512, 1024]
    png_cache: dict[int, bytes] = {}

    for size in sizes:
        image = _render_logo(size)
        png_bytes = image.to_png_bytes()
        png_cache[size] = png_bytes
        (directory / f"patch_gui_logo_primary_{size}.png").write_bytes(png_bytes)

    directory.joinpath("patch_gui_logo_primary.png").write_bytes(png_cache[1024])
    ico_path = directory / "patch_gui_logo_primary.ico"
    ico_path.write_bytes(_build_ico([(size, png_cache[size]) for size in sizes if size <= 256]))


def _build_ico(entries: Iterable[tuple[int, bytes]]) -> bytes:
    entries = list(entries)
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory_entries = []
    images: list[bytes] = []
    for size, data in entries:
        width = size if size < 256 else 0
        height = size if size < 256 else 0
        directory_entries.append(
            struct.pack(
                "<BBBBHHII",
                width,
                height,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        images.append(data)
        offset += len(data)
    return header + b"".join(directory_entries) + b"".join(images)


def main() -> None:
    output = Path(__file__).resolve().parent / "images"
    _save_logo_set(output)


if __name__ == "__main__":
    main()
