"""Generates the Hearts of Iron IV mod (script, GUI, sprites, localisation) from rules/hoi4.toml.

Runtime state lives on the player's country:
  flag npa_panel_open        the Advisor panel is open
  flag npa_debug_show_all    "Show all icons" calibration mode
  flag npa_snooze_<rule>     the rule is snoozed (set with a duration)
  var  npa_tab               selected panel tab (0-based, in [categories] order)
  var  npa_guide             1-based index of the rule whose guide is open (0 = closed)
  var  npa_step              current guide step (1-based)
"""
import math
import os
import re
import shutil

import art
from dds import write_dds

# Panel layout (pixels)
CARD_W, CARD_H, GAP, HEADER_H, FOOTER_H = 420, 76, 10, 52, 44
TAB_H, TAB_GAP, COLUMNS, MAX_PER_CATEGORY = 30, 6, 2, 10
TOPBAR_BADGE, PANEL_BADGE, TOGGLE_SIZE, ALERT_SIZE = 20, 26, 40, 16
FOOTER_BUTTON_W, FOOTER_BUTTON_H = 170, 28
# Guide window layout
GUIDE_W, GUIDE_H, GUIDE_HEADER = 480, 480, 56
STEP_BOX = (12, 64, GUIDE_W - 12, 224)
WHY_BOX = (12, 234, GUIDE_W - 12, GUIDE_H - 56)
GUIDE_BUTTON_W, GUIDE_BUTTON_H = 130, 30
MAX_STEPS = 6


class RulesError(Exception):
    pass


def build(config, out_root):
    mod, rules, targets = config["mod"], config["rule"], config["targets"]
    categories, dlcs = config["categories"], config.get("dlc", {})
    _validate(mod, rules, targets, categories, dlcs)
    p = mod["prefix"]
    for i, rule in enumerate(rules, 1):
        rule["index"] = i

    mod_dir = os.path.join(out_root, mod["folder"])
    if os.path.isdir(mod_dir):
        shutil.rmtree(mod_dir)
    for sub in ("common/scripted_triggers", "common/scripted_guis", "interface", f"gfx/interface/{p}",
                *(f"localisation/{lang}" for lang in LANGUAGES)):
        os.makedirs(os.path.join(mod_dir, sub), exist_ok=True)

    # Order rules within each target by priority; badge for a rule shows only if no earlier one is active.
    by_target = {}
    for rule in sorted(rules, key=lambda r: r["priority"]):
        if rule["target"] != "none":
            by_target.setdefault(rule["target"], []).append(rule)
    by_category = {cat: [r for r in rules if r["category"] == cat] for cat in categories}

    layout = _panel_layout(by_category)
    files = {
        "descriptor.mod": _descriptor(mod, with_path=None),
        f"common/scripted_triggers/{p}_advisor_triggers.txt": _scripted_triggers(p, rules, by_target, dlcs),
        f"common/scripted_guis/{p}_advisor_scripted_guis.txt": _scripted_guis(mod, rules, by_target, categories),
        f"interface/{p}_advisor.gui": _gui(config, by_target, by_category, layout),
        f"interface/{p}_advisor.gfx": _gfx(p),
        **_localisations(mod, rules, targets, categories, config["locale"]),
    }
    for rel, text in files.items():
        # HOI4 requires a UTF-8 BOM on localisation; it is harmless elsewhere so only add it there.
        encoding = "utf-8-sig" if rel.endswith(".yml") else "utf-8"
        with open(os.path.join(mod_dir, rel), "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        if rel.endswith((".txt", ".gui", ".gfx")):
            _check_braces(rel, text)

    _textures(os.path.join(mod_dir, "gfx", "interface", p), layout)

    # The launcher looks for <folder>.mod next to the mod folder, pointing at it by path.
    with open(os.path.join(out_root, mod["folder"] + ".mod"), "w", encoding="utf-8", newline="\n") as f:
        f.write(_descriptor(mod, with_path=f"mod/{mod['folder']}"))
    return mod_dir


# --------------------------------------------------------------------------- validation

def _validate(mod, rules, targets, categories, dlcs):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", mod["prefix"]):
        raise RulesError("mod.prefix must be lowercase letters, digits and underscores")
    seen = set()
    for rule in rules:
        rid = rule.get("id", "?")
        for key in ("id", "category", "target", "priority", "title", "advice", "why", "steps", "trigger"):
            if key not in rule:
                raise RulesError(f"rule '{rid}' is missing '{key}'")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", rid):
            raise RulesError(f"rule id '{rid}' must be lowercase letters, digits and underscores")
        if rid in seen:
            raise RulesError(f"duplicate rule id '{rid}'")
        seen.add(rid)
        if rule["target"] != "none" and rule["target"] not in targets:
            raise RulesError(f"rule '{rid}' targets unknown button '{rule['target']}'")
        if rule["category"] not in categories:
            raise RulesError(f"rule '{rid}' has unknown category '{rule['category']}'")
        if "dlc" in rule and rule["dlc"] not in dlcs:
            raise RulesError(f"rule '{rid}' names unknown dlc '{rule['dlc']}' (add it to [dlc])")
        if not 1 <= len(rule["steps"]) <= MAX_STEPS:
            raise RulesError(f"rule '{rid}' must have 1–{MAX_STEPS} steps")
        for key in ("title", "advice", "why"):
            _check_text(f"rule '{rid}' {key}", rule[key])
        for step in rule["steps"]:
            _check_text(f"rule '{rid}' step", step)
        _check_braces(f"rule '{rid}' trigger", rule["trigger"])
    for cat in categories:
        count = sum(r["category"] == cat for r in rules)
        if count > MAX_PER_CATEGORY:
            raise RulesError(f"category '{cat}' has {count} rules; the panel fits {MAX_PER_CATEGORY} per tab")


def _check_text(where, text):
    if '"' in text:
        raise RulesError(f"{where} may not contain double quotes")


def _check_braces(where, text):
    depth = 0
    for line in text.splitlines():
        for ch in line.split("#", 1)[0]:
            depth += (ch == "{") - (ch == "}")
            if depth < 0:
                raise RulesError(f"{where}: unexpected '}}'")
    if depth:
        raise RulesError(f"{where}: {depth} unclosed '{{'")


# --------------------------------------------------------------------------- script

HEADER_COMMENT = "# Generated from rules/hoi4.toml by tools/build.py — edit the rules, not this file.\n\n"


def _indent(text, tabs):
    pad = "\t" * tabs
    return "\n".join(pad + line if line.strip() else "" for line in text.strip().splitlines())


def _scripted_triggers(p, rules, by_target, dlcs):
    out = [HEADER_COMMENT]
    for key, name in dlcs.items():
        out.append(f"{p}_dlc_{key} = {{\n\thas_dlc = \"{name}\"\n}}\n")
    for rule in rules:
        dlc = f"\t{p}_dlc_{rule['dlc']} = yes\n" if "dlc" in rule else ""
        out.append(
            f"# {rule['title']}\n"
            f"{p}_rule_{rule['id']} = {{\n"
            f"\tNOT = {{ has_country_flag = {p}_snooze_{rule['id']} }}\n"
            f"{dlc}"
            f"{_indent(rule['trigger'], 1)}\n"
            f"}}\n"
        )
    for target_rules in by_target.values():
        for i, rule in enumerate(target_rules):
            earlier = "".join(f"\t\t\t\t{p}_rule_{r['id']} = yes\n" for r in target_rules[:i])
            blocked = f"\t\t\tNOT = {{\n{earlier}\t\t\t}}\n" if earlier else ""
            out.append(
                f"{p}_show_{rule['id']} = {{\n"
                f"\tOR = {{\n"
                f"\t\thas_country_flag = {p}_debug_show_all\n"
                f"\t\tAND = {{\n"
                f"\t\t\t{p}_rule_{rule['id']} = yes\n"
                f"{blocked}"
                f"\t\t}}\n"
                f"\t}}\n"
                f"}}\n"
            )
    any_active = "".join(f"\t\t{p}_rule_{r['id']} = yes\n" for r in rules)
    out.append(f"{p}_any_active = {{\n\tOR = {{\n{any_active}\t}}\n}}\n")
    return "\n".join(out)


def _toggle_flag(flag):
    return (f"if = {{ limit = {{ has_country_flag = {flag} }} clr_country_flag = {flag} }}\n"
            f"\t\t\t\telse = {{ set_country_flag = {flag} }}")


def _open_guide(p, rule):
    return (f"set_variable = {{ {p}_guide = {rule['index']} }}\n"
            f"\t\t\t\tset_variable = {{ {p}_step = 1 }}")


def _snooze(p, rule, days):
    return f"set_country_flag = {{ flag = {p}_snooze_{rule['id']} days = {days} value = 1 }}"


def _scripted_gui(name, window, body, parent=None, visible=None):
    parent_line = f"\t\tparent_window_token = {parent}\n" if parent else ""
    visible_block = f"\t\tvisible = {{ {visible} }}\n" if visible else ""
    return (f"\t{name} = {{\n"
            f"\t\tcontext_type = player_context\n"
            f"\t\twindow_name = \"{window}\"\n"
            f"{parent_line}{visible_block}{body}"
            f"\t}}\n")


def _section(name, entries):
    inner = "".join(f"\t\t\t{key} = {{\n\t\t\t\t{value}\n\t\t\t}}\n" for key, value in entries)
    return f"\t\t{name} = {{\n{inner}\t\t}}\n"


def _scripted_guis(mod, rules, by_target, categories):
    p, parent, days = mod["prefix"], mod["parent_window_token"] or None, mod["snooze_days"]
    guis = []

    guis.append(_scripted_gui(
        f"{p}_toggle", f"{p}_toggle_window",
        _section("effects", [(f"{p}_toggle_button_click", _toggle_flag(f"{p}_panel_open"))]) +
        _section("triggers", [(f"{p}_toggle_alert_visible", f"{p}_any_active = yes")]),
        parent=parent,
    ))

    # Topbar badges: left-click opens that rule's guide, right-click snoozes it.
    for target, target_rules in by_target.items():
        effects, triggers = [], []
        for rule in target_rules:
            rid = rule["id"]
            effects.append((f"{p}_badge_{rid}_click", _open_guide(p, rule)))
            effects.append((f"{p}_badge_{rid}_right_click", _snooze(p, rule, days)))
            triggers.append((f"{p}_badge_{rid}_visible", f"{p}_show_{rid} = yes"))
        guis.append(_scripted_gui(
            f"{p}_target_{target}", f"{p}_target_{target}_window",
            _section("effects", effects) + _section("triggers", triggers),
            parent=parent,
        ))

    # Panel: tabs of rule cards. Clicking a card swaps the panel for that rule's guide.
    effects = [
        (f"{p}_close_button_click", f"clr_country_flag = {p}_panel_open"),
        (f"{p}_debug_button_click", _toggle_flag(f"{p}_debug_show_all")),
    ]
    triggers = []
    for k, cat in enumerate(categories):
        effects.append((f"{p}_tab_{cat}_click", f"set_variable = {{ {p}_tab = {k} }}"))
        triggers.append((f"{p}_tab_{cat}_active_visible", f"check_variable = {{ {p}_tab = {k} }}"))
    tab_index = {cat: k for k, cat in enumerate(categories)}
    for rule in rules:
        rid = rule["id"]
        snoozed = f"has_country_flag = {p}_snooze_{rid}"
        dlc = f" {p}_dlc_{rule['dlc']} = yes" if "dlc" in rule else ""
        effects.append((f"{p}_card_{rid}_button_click",
                        f"{_open_guide(p, rule)}\n\t\t\t\tclr_country_flag = {p}_panel_open"))
        effects.append((f"{p}_row_{rid}_active_right_click", _snooze(p, rule, days)))
        effects.append((f"{p}_row_{rid}_snoozed_click", f"clr_country_flag = {p}_snooze_{rid}"))
        triggers.append((f"{p}_card_{rid}_visible",
                         f"check_variable = {{ {p}_tab = {tab_index[rule['category']]} }}{dlc}"))
        triggers.append((f"{p}_row_{rid}_active_visible", f"{p}_rule_{rid} = yes"))
        triggers.append((f"{p}_row_{rid}_snoozed_visible", snoozed))
        triggers.append((f"{p}_row_{rid}_ok_visible", f"{p}_rule_{rid} = no NOT = {{ {snoozed} }}"))
    guis.append(_scripted_gui(
        f"{p}_panel", f"{p}_panel_window",
        _section("effects", effects) + _section("triggers", triggers),
        visible=f"has_country_flag = {p}_panel_open",
    ))

    # Guide: one page per rule, one text per step; only the current rule and step are visible.
    def on_step(cmp):
        return "OR = { " + " ".join(
            f"AND = {{ check_variable = {{ {p}_guide = {r['index']} }} "
            f"check_variable = {{ {p}_step {cmp(len(r['steps']))} }} }}" for r in rules) + " }"

    effects = [
        (f"{p}_guide_close_click", f"set_variable = {{ {p}_guide = 0 }}"),
        (f"{p}_guide_back_click", f"subtract_from_variable = {{ {p}_step = 1 }}"),
        (f"{p}_guide_next_click", f"add_to_variable = {{ {p}_step = 1 }}"),
        (f"{p}_guide_done_click", f"set_variable = {{ {p}_guide = 0 }}"),
        (f"{p}_guide_all_click", f"set_variable = {{ {p}_guide = 0 }}\n\t\t\t\tset_country_flag = {p}_panel_open"),
    ]
    triggers = [
        (f"{p}_guide_back_visible", f"check_variable = {{ {p}_step > 1 }}"),
        (f"{p}_guide_next_visible", on_step(lambda n: f"< {n}")),
        (f"{p}_guide_done_visible", on_step(lambda n: f"= {n}")),
    ]
    for rule in rules:
        rid = rule["id"]
        triggers.append((f"{p}_guide_{rid}_visible", f"check_variable = {{ {p}_guide = {rule['index']} }}"))
        for s in range(1, len(rule["steps"]) + 1):
            triggers.append((f"{p}_guide_{rid}_step_{s}_visible", f"check_variable = {{ {p}_step = {s} }}"))
    guis.append(_scripted_gui(
        f"{p}_guide", f"{p}_guide_window",
        _section("effects", effects) + _section("triggers", triggers),
        visible=f"check_variable = {{ {p}_guide > 0 }}",
    ))

    return HEADER_COMMENT + "scripted_gui = {\n" + "\n".join(guis) + "}\n"


# --------------------------------------------------------------------------- interface

def _panel_layout(by_category):
    n_tabs = len(by_category)
    width = GAP + COLUMNS * (CARD_W + GAP)
    tab_w = (width - 2 * GAP - (n_tabs - 1) * TAB_GAP) // n_tabs
    tabs_y = HEADER_H + 8
    cards_y = tabs_y + TAB_H + 10
    rows = math.ceil(max(len(r) for r in by_category.values()) / COLUMNS)
    height = cards_y + rows * (CARD_H + GAP) + FOOTER_H
    cards = {}
    for cat_rules in by_category.values():
        for i, rule in enumerate(cat_rules):
            cards[rule["id"]] = (GAP + (i % COLUMNS) * (CARD_W + GAP), cards_y + (i // COLUMNS) * (CARD_H + GAP))
    tabs = {cat: (GAP + k * (tab_w + TAB_GAP), tabs_y) for k, cat in enumerate(by_category)}
    return {"width": width, "height": height, "cards": cards, "tabs": tabs, "tab_w": tab_w}


def _pos(x, y):
    return f"position = {{ x = {x} y = {y} }}"


def _button(name, x, y, sprite, tooltip=None, label=None):
    tt = f"\n\t\t\tpdx_tooltip = \"{tooltip}\"" if tooltip else ""
    text = f"\n\t\t\tbuttonText = \"{label}\"\n\t\t\tbuttonFont = \"hoi_16mbs\"" if label else ""
    return (f"\t\tbuttonType = {{\n\t\t\tname = \"{name}\"\n\t\t\t{_pos(x, y)}\n"
            f"\t\t\tspriteType = \"{sprite}\"{tt}{text}\n\t\t}}\n")


def _icon(name, x, y, sprite, transparent=False):
    extra = "\n\t\t\talwaystransparent = yes" if transparent else ""
    return (f"\t\ticonType = {{\n\t\t\tname = \"{name}\"\n\t\t\t{_pos(x, y)}\n"
            f"\t\t\tspriteType = \"{sprite}\"{extra}\n\t\t}}\n")


def _text(name, x, y, text, font, width, height, fmt="left"):
    return (f"\t\tinstantTextBoxType = {{\n\t\t\tname = \"{name}\"\n\t\t\t{_pos(x, y)}\n"
            f"\t\t\tfont = \"{font}\"\n\t\t\ttext = \"{text}\"\n"
            f"\t\t\tmaxWidth = {width}\n\t\t\tmaxHeight = {height}\n\t\t\tformat = {fmt}\n\t\t}}\n")


def _window(name, x, y, w, h, body, orientation="UPPER_LEFT", moveable=False):
    return (f"\tcontainerWindowType = {{\n\t\tname = \"{name}\"\n\t\t{_pos(x, y)}\n"
            f"\t\tsize = {{ width = {w} height = {h} }}\n\t\torientation = {orientation}\n"
            f"\t\tmoveable = {'yes' if moveable else 'no'}\n\n{body}\t}}\n")


def _gui(config, by_target, by_category, layout):
    mod, toggle, targets, guide = config["mod"], config["toggle"], config["targets"], config["guide"]
    p = mod["prefix"]
    rules = [r for cat_rules in by_category.values() for r in cat_rules]
    windows = []

    # Advisor button. Kept as a small window so it never covers vanilla buttons.
    body = _button(f"{p}_toggle_button", 0, ALERT_SIZE // 2, f"GFX_{p}_advisor_button", f"{p}_toggle_tt")
    body += _icon(f"{p}_toggle_alert", TOGGLE_SIZE - ALERT_SIZE // 2, 0, f"GFX_{p}_badge_small", transparent=True)
    size = TOGGLE_SIZE + ALERT_SIZE // 2
    windows.append(_window(f"{p}_toggle_window", toggle["x"], toggle["y"], size, size, body))

    # One badge-sized window per topbar button; its badges are stacked and only one is visible at a time.
    for target, target_rules in by_target.items():
        t = targets[target]
        body = "".join(_button(f"{p}_badge_{r['id']}", 0, 0, f"GFX_{p}_badge", f"{p}_{r['id']}_tt")
                       for r in target_rules)
        windows.append(_window(f"{p}_target_{target}_window", t["x"], t["y"], TOPBAR_BADGE, TOPBAR_BADGE, body))

    # The Advisor panel: tabs, then one card per rule (cards of other tabs are hidden).
    w, h = layout["width"], layout["height"]
    body = _icon(f"{p}_panel_bg", 0, 0, f"GFX_{p}_panel_bg")
    body += _text(f"{p}_panel_title", 18, 10, f"{p}_panel_title", "hoi_20bs", w - 80, 24)
    body += _text(f"{p}_panel_subtitle", 18, 31, f"{p}_panel_subtitle", "hoi_16mbs", w - 80, 18)
    body += _button(f"{p}_close_button", w - 36, 12, f"GFX_{p}_close_button", f"{p}_close_tt")
    for cat, (tx, ty) in layout["tabs"].items():
        body += _button(f"{p}_tab_{cat}", tx, ty, f"GFX_{p}_tab", label=f"{p}_tab_{cat}")
        body += _icon(f"{p}_tab_{cat}_active", tx, ty, f"GFX_{p}_tab_active", transparent=True)
    for rule in rules:
        rid = rule["id"]
        cx, cy = layout["cards"][rid]
        bx, by = 10, (CARD_H - PANEL_BADGE) // 2
        tx = 20 + PANEL_BADGE
        card = _button(f"{p}_card_{rid}_button", 0, 0, f"GFX_{p}_card", f"{p}_{rid}_card_tt")
        card += _button(f"{p}_row_{rid}_active", bx, by, f"GFX_{p}_badge_panel", f"{p}_{rid}_row_tt")
        card += _button(f"{p}_row_{rid}_snoozed", bx, by, f"GFX_{p}_snoozed", f"{p}_{rid}_snoozed_tt")
        card += _icon(f"{p}_row_{rid}_ok", bx, by, f"GFX_{p}_ok")
        card += _text(f"{p}_row_{rid}_title", tx, 8, f"{p}_{rid}_title", "hoi_18mbs", CARD_W - tx - 10, 22)
        card += _text(f"{p}_row_{rid}_desc", tx, 30, f"{p}_{rid}_desc", "hoi_16mbs", CARD_W - tx - 10, 40)
        body += _window(f"{p}_card_{rid}", cx, cy, CARD_W, CARD_H, card)
    fy = h - FOOTER_H + (FOOTER_H - FOOTER_BUTTON_H) // 2
    body += _button(f"{p}_debug_button", GAP + 2, fy, f"GFX_{p}_text_button", f"{p}_debug_tt", f"{p}_debug_label")
    body += _text(f"{p}_footer_hint", GAP + FOOTER_BUTTON_W + 16, fy + 6, f"{p}_footer_hint", "hoi_16mbs",
                  w - FOOTER_BUTTON_W - 40, 18)
    windows.append(_window(f"{p}_panel_window", -w // 2, -h // 2, w, h, body, orientation="CENTER", moveable=True))

    # The guide: one page per rule; each page holds the title, every step, and the explanation.
    body = _icon(f"{p}_guide_bg", 0, 0, f"GFX_{p}_guide_bg")
    body += _text(f"{p}_guide_subtitle", 18, 34, f"{p}_guide_subtitle", "hoi_16mbs", GUIDE_W - 80, 18)
    text_w = GUIDE_W - 2 * (STEP_BOX[0] + 12)
    for rule in rules:
        rid = rule["id"]
        page = _text(f"{p}_guide_{rid}_title", 18, 10, f"{p}_{rid}_title", "hoi_20bs", GUIDE_W - 80, 24)
        for s in range(1, len(rule["steps"]) + 1):
            page += _text(f"{p}_guide_{rid}_step_{s}", STEP_BOX[0] + 12, STEP_BOX[1] + 10,
                          f"{p}_{rid}_step_{s}", "hoi_18mbs", text_w, STEP_BOX[3] - STEP_BOX[1] - 16)
        page += _text(f"{p}_guide_{rid}_why", WHY_BOX[0] + 12, WHY_BOX[1] + 10,
                      f"{p}_{rid}_why_text", "hoi_16mbs", text_w, WHY_BOX[3] - WHY_BOX[1] - 16)
        body += _window(f"{p}_guide_{rid}", 0, 0, GUIDE_W, WHY_BOX[3], page)
    by = GUIDE_H - 12 - GUIDE_BUTTON_H
    sprite = f"GFX_{p}_guide_button"
    body += _button(f"{p}_guide_close", GUIDE_W - 36, 12, f"GFX_{p}_close_button", f"{p}_close_tt")
    body += _button(f"{p}_guide_back", 14, by, sprite, label=f"{p}_guide_back")
    body += _button(f"{p}_guide_all", (GUIDE_W - GUIDE_BUTTON_W) // 2, by, sprite, label=f"{p}_guide_all")
    body += _button(f"{p}_guide_next", GUIDE_W - 14 - GUIDE_BUTTON_W, by, sprite, label=f"{p}_guide_next")
    body += _button(f"{p}_guide_done", GUIDE_W - 14 - GUIDE_BUTTON_W, by, sprite, label=f"{p}_guide_done")
    windows.append(_window(f"{p}_guide_window", guide["x"], guide["y"], GUIDE_W, GUIDE_H, body,
                           orientation="UPPER_RIGHT", moveable=True))

    return HEADER_COMMENT + "guiTypes = {\n" + "\n".join(windows) + "}\n"


SPRITES = ["badge", "badge_small", "badge_panel", "ok", "snoozed", "advisor_button", "close_button",
           "text_button", "panel_bg", "card", "tab", "tab_active", "guide_bg", "guide_button"]
CLICKABLE = {"badge", "badge_panel", "snoozed", "advisor_button", "close_button", "text_button", "card", "tab",
             "guide_button"}


def _gfx(p):
    entries = []
    for name in SPRITES:
        fx = '\n\t\teffectFile = "gfx/FX/buttonstate.lua"' if name in CLICKABLE else ""
        entries.append(f"\tspriteType = {{\n\t\tname = \"GFX_{p}_{name}\"\n"
                       f"\t\ttexturefile = \"gfx/interface/{p}/{name}.dds\"{fx}\n\t}}\n")
    return "spriteTypes = {\n" + "\n".join(entries) + "}\n"


def _textures(out_dir, layout):
    canvases = {
        "badge": art.advice_badge(TOPBAR_BADGE),
        "badge_small": art.advice_badge(ALERT_SIZE),
        "badge_panel": art.advice_badge(PANEL_BADGE),
        "ok": art.ok_badge(PANEL_BADGE),
        "snoozed": art.snoozed_badge(PANEL_BADGE),
        "advisor_button": art.advisor_button(TOGGLE_SIZE),
        "close_button": art.close_button(24),
        "text_button": art.text_button(FOOTER_BUTTON_W, FOOTER_BUTTON_H),
        "panel_bg": art.panel_background(layout["width"], layout["height"], HEADER_H),
        "card": art.card(CARD_W, CARD_H),
        "tab": art.text_button(layout["tab_w"], TAB_H),
        "tab_active": art.tab_highlight(layout["tab_w"], TAB_H),
        "guide_bg": art.panel_background(GUIDE_W, GUIDE_H, GUIDE_HEADER, boxes=[STEP_BOX, WHY_BOX]),
        "guide_button": art.text_button(GUIDE_BUTTON_W, GUIDE_BUTTON_H),
    }
    assert set(canvases) == set(SPRITES)
    for name, canvas in canvases.items():
        write_dds(os.path.join(out_dir, name + ".dds"), canvas.width, canvas.height, canvas.pixels)


# --------------------------------------------------------------------------- localisation & descriptor

# HOI4 only loads the file for the language the game runs in; it never falls back to English.
# So every language gets a file, using English for anything not translated yet.
LANGUAGES = ["english", "simp_chinese", "braz_por", "french", "german", "japanese", "polish", "russian", "spanish"]


def _validate_locales(locales, rules, targets, categories):
    if "english" not in locales:
        raise RulesError("rules/locale/hoi4/english.toml is missing")
    by_id = {r["id"]: r for r in rules}
    for lang, loc in locales.items():
        if lang not in LANGUAGES:
            raise RulesError(f"locale '{lang}' is not a HOI4 language (expected one of {', '.join(LANGUAGES)})")
        for key in ("ui", "targets", "categories", "rules"):
            known = {"ui": locales["english"]["ui"], "targets": targets, "categories": categories,
                     "rules": by_id}[key]
            for name in loc.get(key, {}):
                if name not in known:
                    raise RulesError(f"locale '{lang}': unknown {key} entry '{name}'")
        for value in [*loc.get("ui", {}).values(), *loc.get("targets", {}).values(),
                      *loc.get("categories", {}).values()]:
            _check_text(f"locale '{lang}'", value)
        for rid, text in loc.get("rules", {}).items():
            for field, value in text.items():
                if field not in ("title", "advice", "why", "steps"):
                    raise RulesError(f"locale '{lang}': rule '{rid}' has unknown field '{field}'")
                for v in value if field == "steps" else [value]:
                    _check_text(f"locale '{lang}': rule '{rid}' {field}", v)
            if "steps" in text and len(text["steps"]) != len(by_id[rid]["steps"]):
                raise RulesError(f"locale '{lang}': rule '{rid}' has {len(text['steps'])} steps, "
                                 f"English has {len(by_id[rid]['steps'])}")


def _localisations(mod, rules, targets, categories, locales):
    """Returns {relative path: file text} for every HOI4 language."""
    _validate_locales(locales, rules, targets, categories)
    english = locales["english"]
    return {f"localisation/{lang}/{mod['prefix']}_advisor_l_{lang}.yml":
            _localisation(lang, mod, rules, targets, categories, english, locales.get(lang, {}))
            for lang in LANGUAGES}


def _localisation(lang, mod, rules, targets, categories, english, loc):
    p, days = mod["prefix"], mod["snooze_days"]
    ui = {**english["ui"], **loc.get("ui", {})}

    def fmt(key, **kw):
        return ui[key].format(days=days, **kw)

    entries = {f"{p}_{key}": fmt(key) for key in
               ("toggle_tt", "close_tt", "panel_title", "panel_subtitle", "debug_label", "debug_tt", "footer_hint",
                "guide_subtitle", "guide_back", "guide_next", "guide_done", "guide_all")}
    for cat, label in categories.items():
        entries[f"{p}_tab_{cat}"] = loc.get("categories", {}).get(cat, label)
    for rule in rules:
        rid = rule["id"]
        text = {**{k: rule[k] for k in ("title", "advice", "why", "steps")}, **loc.get("rules", {}).get(rid, {})}
        if rule["target"] == "none":
            label = fmt("none_label")
        else:
            label = loc.get("targets", {}).get(rule["target"], targets[rule["target"]]["label"])
        body = f"§Y{text['title']}§!\n{text['advice']}\n\n{text['why']}"
        entries[f"{p}_{rid}_title"] = text["title"]
        entries[f"{p}_{rid}_desc"] = f"{text['advice']} {fmt('desc_where', label=label)}"
        entries[f"{p}_{rid}_tt"] = f"{body}\n\n{fmt('badge_hint', label=label)}"
        entries[f"{p}_{rid}_row_tt"] = f"{body}\n\n{fmt('row_hint')}"
        entries[f"{p}_{rid}_card_tt"] = f"§Y{text['title']}§!\n{text['advice']}\n\n{fmt('card_tt')}"
        entries[f"{p}_{rid}_snoozed_tt"] = fmt("snoozed_tt", title=text["title"])
        total = len(text["steps"])
        for n, step in enumerate(text["steps"], 1):
            entries[f"{p}_{rid}_step_{n}"] = f"§Y{fmt('guide_step', n=n, total=total)}§!\n\n{step}"
        entries[f"{p}_{rid}_why_text"] = f"§Y{fmt('guide_why')}§!\n{text['why']}"
    lines = [f"l_{lang}:"] + [f' {key}:0 "{value.strip()}"'.replace("\n", "\\n") for key, value in entries.items()]
    return "\n".join(lines) + "\n"


def _descriptor(mod, with_path):
    lines = [
        f'version="{mod["version"]}"',
        'tags={\n\t"Gameplay"\n}',
        f'name="{mod["name"]}"',
        f'supported_version="{mod["supported_version"]}"',
    ]
    if with_path:
        lines.append(f'path="{with_path}"')
    return "\n".join(lines) + "\n"
