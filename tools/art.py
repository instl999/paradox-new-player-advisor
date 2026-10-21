"""Procedural icon art for the advisor, drawn with signed-distance shapes so no image editor is needed.

Every shape is a function (x, y) -> signed distance in pixels (negative = inside).
"""
import math


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def rgba(r, g, b, a=255):
    return (r / 255, g / 255, b / 255, a / 255)


def vertical(top, bottom, y0, y1):
    """Colour callable: linear gradient from `top` at y0 to `bottom` at y1."""
    return lambda x, y: _mix(top, bottom, _clamp((y - y0) / max(1e-6, y1 - y0)))


# --- shapes ---------------------------------------------------------------

def circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def capsule(ax, ay, bx, by, r):
    def d(x, y):
        pax, pay, bax, bay = x - ax, y - ay, bx - ax, by - ay
        h = _clamp((pax * bax + pay * bay) / (bax * bax + bay * bay))
        return math.hypot(pax - bax * h, pay - bay * h) - r
    return d


def round_rect(x0, y0, x1, y1, rad):
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 - rad, (y1 - y0) / 2 - rad

    def d(x, y):
        qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
        return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - rad
    return d


def union(*shapes):
    return lambda x, y: min(s(x, y) for s in shapes)


# --- canvas ---------------------------------------------------------------

class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.pixels = [(0.0, 0.0, 0.0, 0.0)] * (width * height)

    def fill(self, shape, color, bbox=None):
        """Composite `color` (tuple or callable(x, y)) over the canvas wherever `shape` is inside."""
        x0, y0, x1, y1 = bbox or (0, 0, self.width, self.height)
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(self.width, int(math.ceil(x1))), min(self.height, int(math.ceil(y1)))
        for py in range(y0, y1):
            for px in range(x0, x1):
                x, y = px + 0.5, py + 0.5
                coverage = _clamp(0.5 - shape(x, y))
                if coverage <= 0:
                    continue
                src = color(x, y) if callable(color) else color
                self._over(py * self.width + px, src, coverage)

    def _over(self, i, src, coverage):
        dr, dg, db, da = self.pixels[i]
        sa = src[3] * coverage
        oa = sa + da * (1 - sa)
        if oa <= 0:
            return
        k = da * (1 - sa)
        self.pixels[i] = (
            (src[0] * sa + dr * k) / oa,
            (src[1] * sa + dg * k) / oa,
            (src[2] * sa + db * k) / oa,
            oa,
        )


# --- icons ----------------------------------------------------------------

GOLD_TOP, GOLD_BOTTOM = rgba(255, 214, 90), rgba(214, 132, 18)
INK = rgba(44, 26, 4)


def _disc(c, size, edge, top, bottom):
    m = size / 2
    c.fill(circle(m, m, m - 0.5), edge)
    c.fill(circle(m, m, m - 0.5 - size * 0.075), vertical(top, bottom, 0, size))


def advice_badge(size):
    """Gold disc with an exclamation mark: 'the advisor recommends something here'."""
    s, c = size / 24, Canvas(size, size)
    _disc(c, size, INK, GOLD_TOP, GOLD_BOTTOM)
    c.fill(capsule(12 * s, 6.3 * s, 12 * s, 12.8 * s, 1.7 * s), INK)
    c.fill(circle(12 * s, 17.3 * s, 1.85 * s), INK)
    return c


def ok_badge(size):
    s, c = size / 24, Canvas(size, size)
    _disc(c, size, rgba(14, 50, 20), rgba(120, 200, 110), rgba(40, 125, 55))
    white = rgba(245, 255, 240)
    c.fill(union(capsule(7 * s, 12.5 * s, 10.5 * s, 16 * s, 1.6 * s),
                 capsule(10.5 * s, 16 * s, 17 * s, 8.5 * s, 1.6 * s)), white)
    return c


def snoozed_badge(size):
    s, c = size / 24, Canvas(size, size)
    _disc(c, size, rgba(30, 30, 36), rgba(150, 155, 170), rgba(90, 95, 110))
    ink = rgba(30, 32, 40)
    c.fill(union(capsule(8 * s, 8 * s, 16 * s, 8 * s, 1.4 * s),
                 capsule(16 * s, 8 * s, 8 * s, 16 * s, 1.4 * s),
                 capsule(8 * s, 16 * s, 16 * s, 16 * s, 1.4 * s)), ink)
    return c


def advisor_button(size):
    """Topbar button that opens the advisor panel: a lightbulb on a navy tile."""
    s, c = size / 40, Canvas(size, size)
    c.fill(round_rect(1, 1, size - 1, size - 1, 7 * s), vertical(GOLD_TOP, GOLD_BOTTOM, 0, size))
    c.fill(round_rect(3.5 * s, 3.5 * s, size - 3.5 * s, size - 3.5 * s, 5 * s),
           vertical(rgba(46, 62, 96), rgba(18, 24, 40), 0, size))
    c.fill(circle(20 * s, 16.5 * s, 8.5 * s), rgba(255, 240, 160))
    c.fill(circle(20 * s, 16.5 * s, 5.5 * s), rgba(255, 252, 225))
    c.fill(round_rect(15.5 * s, 22 * s, 24.5 * s, 30.5 * s, 2 * s), rgba(170, 175, 185))
    c.fill(capsule(15.5 * s, 25.5 * s, 24.5 * s, 25.5 * s, 0.6 * s), rgba(90, 95, 110))
    c.fill(capsule(17.5 * s, 32.5 * s, 22.5 * s, 32.5 * s, 1.2 * s), rgba(170, 175, 185))
    return c


def close_button(size):
    s, c = size / 24, Canvas(size, size)
    c.fill(round_rect(1, 1, size - 1, size - 1, 4 * s), rgba(60, 20, 18))
    c.fill(round_rect(2.5 * s, 2.5 * s, size - 2.5 * s, size - 2.5 * s, 3 * s),
           vertical(rgba(190, 70, 55), rgba(120, 30, 25), 0, size))
    white = rgba(255, 235, 230)
    c.fill(union(capsule(8 * s, 8 * s, 16 * s, 16 * s, 1.6 * s),
                 capsule(16 * s, 8 * s, 8 * s, 16 * s, 1.6 * s)), white)
    return c


def text_button(width, height):
    c = Canvas(width, height)
    c.fill(round_rect(0.5, 0.5, width - 0.5, height - 0.5, 4), rgba(120, 90, 30))
    c.fill(round_rect(2, 2, width - 2, height - 2, 3), vertical(rgba(70, 84, 112), rgba(34, 42, 60), 0, height))
    return c


def panel_background(width, height, header_height, boxes=()):
    """Window frame with a gold border and a header band. `boxes` = inset areas as (x0, y0, x1, y1)."""
    c = Canvas(width, height)
    c.fill(round_rect(0, 0, width, height, 10), vertical(GOLD_TOP, GOLD_BOTTOM, 0, height))
    c.fill(round_rect(2.5, 2.5, width - 2.5, height - 2.5, 8),
           vertical(rgba(30, 36, 50, 245), rgba(14, 17, 24, 245), 0, height))
    c.fill(round_rect(2.5, 2.5, width - 2.5, header_height, 8),
           vertical(rgba(58, 70, 100, 250), rgba(32, 40, 58, 250), 0, header_height))
    c.fill(capsule(14, header_height, width - 14, header_height, 0.7), rgba(214, 160, 50, 200))
    for x0, y0, x1, y1 in boxes:
        c.fill(round_rect(x0, y0, x1, y1, 6), rgba(255, 255, 255, 18), (x0, y0, x1, y1))
        c.fill(round_rect(x0 + 1, y0 + 1, x1 - 1, y1 - 1, 5), rgba(10, 12, 18, 140), (x0, y0, x1, y1))
    return c


def card(width, height):
    """Clickable advice card; the game's button shader brightens it on hover."""
    c = Canvas(width, height)
    c.fill(round_rect(0, 0, width, height, 6), rgba(120, 130, 150, 60))
    c.fill(round_rect(1, 1, width - 1, height - 1, 5), vertical(rgba(36, 42, 56, 235), rgba(20, 24, 33, 235), 0, height))
    return c


def tab_highlight(width, height):
    """Gold outline and underline drawn over the selected tab."""
    c = Canvas(width, height)
    outer, inner = round_rect(0, 0, width, height, 4), round_rect(1.5, 1.5, width - 1.5, height - 1.5, 3)
    c.fill(lambda x, y: max(outer(x, y), -inner(x, y)), rgba(255, 205, 80))
    c.fill(round_rect(6, height - 4, width - 6, height - 1.5, 1), rgba(255, 205, 80))
    return c
