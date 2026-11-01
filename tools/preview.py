"""Renders the generated Victoria 3 interface as an HTML page, so layout and text can be checked without the game.

    python tools/preview.py vic3 [--lang simp_chinese]   # → build/vic3/preview/index.html

It reads the generated .gui files, evaluates each element's `visible` binding for a sample situation (a few rules
active, see SCENARIO), and draws every visible element at its position with its texture and text. Three views:
the HUD with the "Do this next" bar and badges, the open Advisor panel, and an open guide.
This is an approximation (no game fonts, no text formatting, the sidebar is drawn as grey boxes), meant for
checking positions, sizes, overlaps and wording.
"""
import argparse
import html
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build  # noqa: E402
import common  # noqa: E402
import pdx  # noqa: E402
import vic3_backend  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Rules active in the sample situation: an early game with idle research and construction.
SCENARIO = ["no_research", "idle_construction", "goods_shortage", "enact_law", "low_literacy"]
SCREEN = (1920, 1080)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game", choices=["vic3"])
    parser.add_argument("--lang", default="english")
    args = parser.parse_args()

    config = build.load_config(args.game)
    out_root = os.path.join(ROOT, "build", args.game)
    mod_dir = vic3_backend.build(config, out_root)
    preview_dir = os.path.join(out_root, "preview")
    os.makedirs(preview_dir, exist_ok=True)
    loc = _load_loc(mod_dir, args.lang)
    truths = _scripted_gui_truths(config)

    p = config["mod"]["prefix"]
    with open(os.path.join(mod_dir, "gui", f"{p}_advisor_hud.gui"), encoding="utf-8-sig") as f:
        hud = pdx.parse(f.read())
    with open(os.path.join(mod_dir, "gui", f"{p}_advisor_windows.gui"), encoding="utf-8-sig") as f:
        windows = pdx.parse(f.read())

    first_next = next(r["id"] for r in sorted(config["rule"], key=lambda r: r["rank"]) if r["id"] in SCENARIO)
    views = [
        ("HUD: Do this next bar, badges and highlight", {}, hud, True),
        ("Advisor panel (Economy tab)", {"npa_panel": "yes"}, hud + windows, True),
        (f"Guide: {first_next}, step 2 (its button pulses)", {"npa_guide": first_next, "npa_step": "2"},
         hud + windows, True),
    ]
    body = []
    for title, ui_vars, tree, with_sidebar in views:
        renderer = Renderer(mod_dir, preview_dir, loc, truths, ui_vars)
        inner = renderer.render(tree, SCREEN)
        sidebar = _sidebar(config, loc) if with_sidebar else ""
        body.append(f'<h2>{html.escape(title)}</h2><div class="frame"><div class="screen">{sidebar}{inner}</div></div>')
    page = PAGE.format(lang=args.lang, scenario=", ".join(SCENARIO), body="\n".join(body))
    path = os.path.join(preview_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Preview -> {os.path.relpath(path, ROOT)}")


def _load_loc(mod_dir, lang):
    path = os.path.join(mod_dir, "localization", lang, f"npa_advisor_l_{lang}.yml")
    entries = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = re.match(r'^ ([A-Za-z0-9_.]+): "(.*)"$', line.rstrip("\n"))
            if m:
                entries[m.group(1)] = m.group(2)
    return entries


def _scripted_gui_truths(config):
    """Which scripted GUIs report IsShown for the SCENARIO, following the generated triggers' logic."""
    p, rules = config["mod"]["prefix"], config["rule"]
    ranked, by_target = common.rank_rules(rules)
    active = [r for r in ranked if r["id"] in SCENARIO]
    truths = {f"{p}_any_active"} if active else set()
    truths |= {f"{p}_rule_{r['id']}" for r in active}
    if active:
        truths.add(f"{p}_next_{active[0]['id']}")
    for target, target_rules in by_target.items():
        first = next((r for r in target_rules if r["id"] in SCENARIO), None)
        if first:
            truths.add(f"{p}_show_{first['id']}")
        if active and active[0] in target_rules:
            truths.add(f"{p}_target_next_{target}")
    return truths


class Renderer:
    def __init__(self, mod_dir, preview_dir, loc, truths, ui_vars):
        self.mod_dir, self.preview_dir, self.loc = mod_dir, preview_dir, loc
        self.truths, self.vars = truths, ui_vars

    def visible(self, expr):
        if expr is None:
            return True
        e = expr.strip()[1:-1] if expr.strip().startswith("[") else expr
        e = re.sub(r"GetScriptedGui\('([^']+)'\)\.IsShown\([^()]*\([^()]*\)[^()]*\)",
                   lambda m: str(m.group(1) in self.truths), e)
        e = re.sub(r"GetVariableSystem\.Exists\('([^']+)'\)", lambda m: str(m.group(1) in self.vars), e)
        e = re.sub(r"GetVariableSystem\.HasValue\('([^']+)', '([^']*)'\)",
                   lambda m: str(self.vars.get(m.group(1)) == m.group(2)), e)
        for name, value in (("GetPlayer.IsValid", "True"), ("IsInGame", "True"), ("IsPauseMenuShown", "False"),
                            ("IsGameOverScreenShown", "False"), ("InformationPanelBar.IsAnyPanelOpen", "False")):
            e = e.replace(name, value)
        e = e.replace("And(", "_and(").replace("Or(", "_or(").replace("Not(", "_not(")
        return eval(e, {"__builtins__": {}}, {"_and": lambda a, b: a and b, "_or": lambda a, b: a or b,
                                               "_not": lambda a: not a, "True": True, "False": False})

    def render(self, entries, parent_size):
        return "".join(self.element(e.key, e.value, parent_size) for e in entries
                       if e.key in ("widget", "button", "icon", "textbox"))

    def element(self, kind, body, parent_size):
        if not self.visible(pdx.first(body, "visible")):
            return ""
        w, h = _size(pdx.first(body, "size"), parent_size)
        x, y = _pos(pdx.first(body, "position"))
        anchor = pdx.first(body, "parentanchor", "")
        if "center" in anchor:
            x, y = x + (parent_size[0] - w) // 2, y + (parent_size[1] - h) // 2
        elif "right" in anchor:
            x = parent_size[0] + x - w
        style = f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;"
        texture = pdx.first(body, "texture")
        if texture:
            style += f"background-image:url({self.png(texture)});background-size:100% 100%;"
        tip = pdx.first(body, "tooltip")
        title = f' title="{html.escape(_plain(self.loc.get(tip, tip)))}"' if tip else ""
        inner = ""
        if kind == "textbox":
            text = pdx.first(body, "text")
            size = pdx.first(body, "fontsize", "16")
            align = pdx.first(body, "align", "")
            multiline = pdx.first(body, "multiline") == "yes"
            css = (f"font-size:{size}px;text-align:{'center' if 'center' in align else 'left'};"
                   f"white-space:{'normal' if multiline else 'nowrap'};"
                   f"{'' if multiline else 'display:flex;align-items:center;'}"
                   f"justify-content:{'center' if 'center' in align else 'flex-start'};")
            if pdx.first(body, "default_format") == "#header":
                css += "color:#f3d27a;font-weight:600;"
            style += css
            inner = f"<span>{_rich(self.loc.get(text, f'MISSING {text}'))}</span>"
        inner += self.render(body, (w, h))
        if "_pulse_" in pdx.first(body, "name", ""):
            style += "animation:pulse 1.2s ease-in-out infinite;"
        return f'<div class="{kind}" style="{style}"{title}>{inner}</div>'

    def png(self, texture):
        name = os.path.basename(texture)[:-4] + ".png"
        out = os.path.join(self.preview_dir, name)
        if not os.path.exists(out):
            _dds_to_png(os.path.join(self.mod_dir, texture), out)
        return name


def _size(value, parent):
    if not value:
        return parent
    out = []
    for v, p in zip([e.value for e in value], parent):
        out.append(int(p * float(v[:-1]) / 100) if v.endswith("%") else int(v))
    return tuple(out)


def _pos(value):
    if not value:
        return 0, 0
    return tuple(int(e.value) for e in value)


def _plain(text):
    return re.sub(r"#[a-z_]+ |#!", "", text).replace("\\n", "\n")


def _rich(text):
    out = html.escape(text).replace("\\n", "<br>")
    out = re.sub(r"#(header|v|instruction|b) (.*?)#!",
                 lambda m: f'<span class="f-{m.group(1)}">{m.group(2)}</span>', out)
    return out


def _sidebar(config, loc):
    """Grey stand-ins for the vanilla sidebar buttons at their configured boxes."""
    out = ['<div class="sidebar"></div>']
    for name, t in config["targets"].items():
        label = html.escape(t["label"][:3])
        out.append(f'<div class="vanilla" style="left:{t["x"]}px;top:{t["y"]}px;width:{t["w"]}px;'
                   f'height:{t["h"]}px">{label}</div>')
    return "".join(out)


def _dds_to_png(src, dst):
    with open(src, "rb") as f:
        data = f.read()
    height, width = struct.unpack("<2I", data[12:20])
    px = data[128:]
    rows = []
    for y in range(height):
        row = bytearray(b"\0")
        for x in range(width):
            b, g, r, a = px[(y * width + x) * 4:(y * width + x) * 4 + 4]
            row += bytes((r, g, b, a))
        rows.append(bytes(row))

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    with open(dst, "wb") as f:
        f.write(png)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Advisor Preview</title>
<style>
body {{ background:#111; color:#ddd; font-family: Georgia, 'Songti SC', serif; margin:16px; }}
h1 {{ font-size:20px; }} h2 {{ font-size:16px; margin-top:28px; color:#f3d27a; }}
p {{ max-width:900px; color:#aaa; }}
.frame {{ width:960px; height:540px; overflow:hidden; }}
.screen {{ position:relative; width:1920px; height:1080px; transform:scale(0.5); transform-origin:0 0;
          background:linear-gradient(135deg,#3c5a46,#2d4a5c 60%,#40506a); overflow:hidden; }}
.screen div {{ position:absolute; box-sizing:border-box; }}
.textbox {{ color:#eee; line-height:1.25; overflow:hidden; }}
.sidebar {{ left:0; top:183px; width:50px; height:620px; background:#1c1f26; }}
.vanilla {{ background:#555c68; border:1px solid #888; color:#ccc; font:11px sans-serif;
           display:flex; align-items:center; justify-content:center; }}
.f-header {{ color:#f3d27a; font-weight:600; }} .f-v {{ color:#fff2b0; font-weight:600; }}
.f-instruction {{ color:#9fc8a0; font-style:italic; }}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 45% {{ opacity:.25; }} }}
</style></head><body>
<h1>New Player Advisor — Victoria 3 preview ({lang})</h1>
<p>Generated from the built mod by tools/preview.py. Sample situation: these rules are active: {scenario}.
Grey boxes stand in for the vanilla sidebar buttons at the positions configured in rules/vic3.toml.
Hover over elements to see their tooltips. Shown at 50% of a 1920×1080 screen.</p>
{body}
</body></html>
"""

if __name__ == "__main__":
    main()
