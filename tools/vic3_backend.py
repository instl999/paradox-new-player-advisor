"""Generates the Victoria 3 mod (script, GUI, textures, localization, metadata) from rules/vic3.toml.

Victoria 3's interface is Jomini GUI with data binding, so most of the advisor's state is UI-only:
  GetVariableSystem 'npa_panel'      the Advisor panel is open
  GetVariableSystem 'npa_tab'        selected panel tab (category key; unset = first tab)
  GetVariableSystem 'npa_guide'      id of the rule whose guide is open (unset = closed)
  GetVariableSystem 'npa_step'       current guide step ('1', '2', ...)
  GetVariableSystem 'npa_show_all'   calibration mode: every badge and highlight visible
  GetVariableSystem 'npa_hide_next'  the player turned the "Do this next" bar off
Only snoozing touches the game state: a timed country variable npa_snooze_<rule>, set through a scripted GUI.

The GUI reads rule state through scripted GUIs (one per rule and kind: rule / show / next / snoozed), each of which
calls the matching scripted trigger. Two windows are registered in gui/scripted_widgets, so no vanilla .gui file
is overridden: a HUD layer (advisor button, "Do this next" bar, badges and highlights over the sidebar buttons)
and a menu layer (panel and guide). Each rule also gets a native alert that shows while it is "Do this next".
"""
import json
import math
import os
import re
import shutil

import art
import lint
from common import RulesError, check_braces, check_identifier, header_comment, indent, rank_rules
from common import rule_text, validate_locales, validate_rules
from dds import write_dds

GAME_FOLDER = "Victoria 3"  # under Documents/Paradox Interactive and steamapps/common

PACKAGE_README = """{name} {version} - Victoria 3

INSTALL
  1. Unzip this folder anywhere (do not run it from inside the zip).
  2. Double-click Install.bat.
  3. In the Paradox launcher, add "{name}" to a playset and start the game.

UNINSTALL
  Double-click Uninstall.bat.

USING IT
  The bar under the advisor button (top left) always names the most useful thing to do next. Click it for a
  step-by-step guide; the button you need pulses. A gold "!" on a sidebar button means there is advice for that
  screen: hover to read why, left-click for the guide, right-click to snooze it for {days} days.
  The advisor button opens a panel with all advice, sorted into tabs.

  The current "Do this next" advice also appears in the game's own Important Actions list.

  If the badges don't line up with the sidebar buttons, open the Advisor and click "Show all icons" to see every
  badge at once. Then report the offsets (a screenshot helps).

NOTE
  Like any mod, this turns off Ironman achievements while it is enabled.
  If something doesn't work, send:  Documents\\Paradox Interactive\\Victoria 3\\logs\\error.log
"""

# Panel layout (UI pixels at 100% scale)
CARD_W, CARD_H, GAP, HEADER_H, FOOTER_H = 420, 76, 10, 52, 44
TAB_H, TAB_GAP, COLUMNS, MAX_PER_CATEGORY = 30, 6, 2, 10
BADGE, PANEL_BADGE, TOGGLE_SIZE, ALERT_DOT = 20, 26, 40, 16
BANNER_H, NEXT_W, NEXT_H = 36, 340, 32
FOOTER_BUTTON_W, FOOTER_BUTTON_H = 170, 28
GUIDE_W, GUIDE_H, GUIDE_HEADER = 480, 480, 56
STEP_BOX = (12, 64, GUIDE_W - 12, 224)
WHY_BOX = (12, 234, GUIDE_W - 12, GUIDE_H - 56)
GUIDE_BUTTON_H, GUIDE_BUTTON_GAP = 30, 8
GUIDE_BUTTON_W = (GUIDE_W - 28 - 3 * GUIDE_BUTTON_GAP) // 4  # four buttons: Back, Open screen, All advice, Next
MAX_STEPS = 6
GLOW_PAD = 6  # the highlight frame extends this far beyond the button

# Victoria 3 languages. Every one gets a file; untranslated text is English.
LANGUAGES = ["english", "braz_por", "french", "german", "japanese", "korean", "polish", "russian", "simp_chinese",
             "spanish", "turkish"]
# Text keys the .gui references directly; the others are templates used to compose rule text.
GUI_TEXT_KEYS = ("toggle_tt", "close_tt", "panel_title", "panel_subtitle", "debug_label", "debug_tt", "footer_hint",
                 "guide_subtitle", "guide_back", "guide_next", "guide_done", "guide_all", "guide_open",
                 "hide_next_label", "hide_next_tt", "banner_none")
UI_KEYS = GUI_TEXT_KEYS + ("desc_where", "badge_hint", "row_hint", "snoozed_tt", "card_tt", "guide_step", "guide_why",
                           "none_label", "next_prefix", "next_hint", "alert_prefix", "alert_action", "guide_open_tt")

# Like vanilla's hud_visibility template, plus a played country (observers have none, and GetPlayer would fail).
ROOT_VISIBLE = ("[And(GetPlayer.IsValid, And(IsInGame, And(Not(IsPauseMenuShown), Not(IsGameOverScreenShown))))]")
# Panel and guide: above the HUD (layer_ingame_hud = -221, which holds the outliner) but below event popups and
# toasts (-185 / -186). They hide with the pause menu, so they never cover the save and load menus (-219 / -218).
WINDOWS_LAYER = "layer_lens_toolbar"  # priority -201 in gui/layers.gui


def build(config, out_root):
    mod, rules, targets = config["mod"], config["rule"], config["targets"]
    categories, dlcs = config["categories"], config.get("dlc", {})
    _validate(mod, rules, targets, categories, dlcs, config["locale"])
    p = mod["prefix"]
    ranked, by_target = rank_rules(rules)
    by_category = {cat: [r for r in rules if r["category"] == cat] for cat in categories}
    layout = _panel_layout(by_category)

    mod_dir = os.path.join(out_root, mod["folder"])
    if os.path.isdir(mod_dir):
        shutil.rmtree(mod_dir)
    for sub in (".metadata", "common/scripted_triggers", "common/scripted_guis", "common/script_values",
                "common/alert_types", "gui/scripted_widgets", f"gfx/interface/{p}",
                *(f"localization/{lang}" for lang in LANGUAGES)):
        os.makedirs(os.path.join(mod_dir, sub), exist_ok=True)

    files = {
        ".metadata/metadata.json": _metadata(mod),
        f"common/scripted_triggers/{p}_advisor_triggers.txt": _scripted_triggers(p, rules, ranked, by_target, dlcs),
        f"common/scripted_guis/{p}_advisor_scripted_guis.txt": _scripted_guis(mod, rules, by_target),
        f"common/script_values/{p}_advisor_values.txt": _script_values(p),
        f"gui/scripted_widgets/{p}_advisor_widgets.txt":
            f"gui/{p}_advisor_hud.gui = {p}_hud_root\ngui/{p}_advisor_windows.gui = {p}_windows_root\n",
        f"gui/{p}_advisor_hud.gui": _hud_gui(config, by_target),
        f"gui/{p}_advisor_windows.gui": _windows_gui(config, by_category, layout),
        **_localizations(mod, rules, targets, categories, config["locale"]),
    }
    if mod.get("alerts", True):
        files[f"common/alert_types/{p}_advisor_alerts.txt"] = _alert_types(p, rules, targets)
    for rel, text in files.items():
        # Localization needs a UTF-8 BOM; the game's own script and .gui files carry one too.
        encoding = "utf-8-sig" if rel.endswith((".yml", ".txt", ".gui")) else "utf-8"
        with open(os.path.join(mod_dir, rel), "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        if rel.endswith((".txt", ".gui")) and "scripted_widgets" not in rel:
            check_braces(rel, text)

    _textures(os.path.join(mod_dir, "gfx", "interface", p), config, layout)
    return mod_dir


# --------------------------------------------------------------------------- validation

def _validate(mod, rules, targets, categories, dlcs, locales):
    check_identifier("mod.prefix", mod["prefix"])
    validate_rules(rules, targets, categories, dlcs, MAX_STEPS, MAX_PER_CATEGORY)
    lint.check_rules("vic3", rules, scripted={f"{mod['prefix']}_infrastructure_balance"})
    for cat in categories:
        check_identifier("category", cat)
    for name, t in targets.items():
        for key in ("label", "x", "y", "w", "h"):
            if key not in t:
                raise RulesError(f"target '{name}' is missing '{key}'")
        if "open" not in t and "panel" not in t:
            raise RulesError(f"target '{name}' needs 'panel' (and 'tab') or a full 'open' command")
    # Jomini text treats [ ] as data binding, $ as a key reference and # as formatting.
    for lang, loc in locales.items():
        for rule in rules:
            text = rule_text(rule, loc)
            for value in [text["title"], text["advice"], text["why"], *text["steps"]]:
                if re.search(r"[\[\]$#]", value):
                    raise RulesError(f"locale '{lang}': rule '{rule['id']}' text may not contain [ ] $ or #")


# --------------------------------------------------------------------------- script

HEADER_COMMENT = header_comment("vic3")


def _scripted_triggers(p, rules, ranked, by_target, dlcs):
    out = [HEADER_COMMENT]
    for key, feature in dlcs.items():
        out.append(f"{p}_dlc_{key} = {{\n\thas_dlc_feature = {feature}\n}}\n")
    for rule in rules:
        dlc = f"\t{p}_dlc_{rule['dlc']} = yes\n" if "dlc" in rule else ""
        out.append(
            f"# {rule['title']}\n"
            f"{p}_rule_{rule['id']} = {{\n"
            f"\tNOT = {{ has_variable = {p}_snooze_{rule['id']} }}\n"
            f"{dlc}"
            f"{indent(rule['trigger'], 1)}\n"
            f"}}\n"
        )
    # Badge: active, and no higher-ranked rule on the same button is active.
    for target_rules in by_target.values():
        for i, rule in enumerate(target_rules):
            out.append(_first_active(p, "show", rule, target_rules[:i]))
    # "Do this next": active, and no higher-ranked rule anywhere is active.
    for i, rule in enumerate(ranked):
        out.append(_first_active(p, "next", rule, ranked[:i]))
    any_active = "".join(f"\t\t{p}_rule_{r['id']} = yes\n" for r in rules)
    out.append(f"{p}_any_active = {{\n\tOR = {{\n{any_active}\t}}\n}}\n")
    return "\n".join(out)


def _first_active(p, kind, rule, earlier):
    blocked = ""
    if earlier:
        names = "".join(f"\t\t\t{p}_rule_{r['id']} = yes\n" for r in earlier)
        blocked = f"\tNOT = {{\n\t\tOR = {{\n{names}\t\t}}\n\t}}\n"
    return f"{p}_{kind}_{rule['id']} = {{\n\t{p}_rule_{rule['id']} = yes\n{blocked}}}\n"


def _scripted_guis(mod, rules, by_target):
    p, days = mod["prefix"], mod["snooze_days"]
    out = [HEADER_COMMENT]

    def sgui(name, body):
        out.append(f"{name} = {{\n\tscope = country\n{body}}}\n")

    sgui(f"{p}_any_active", f"\tis_shown = {{ {p}_any_active = yes }}\n")
    # Does this button hold the next move? (one check per button for its highlight frame)
    for target, target_rules in by_target.items():
        nexts = " ".join(f"{p}_next_{r['id']} = yes" for r in target_rules)
        sgui(f"{p}_target_next_{target}", f"\tis_shown = {{ OR = {{ {nexts} }} }}\n")
    for rule in rules:
        rid = rule["id"]
        for kind in ("rule", "show", "next"):
            if kind == "show" and rule["target"] == "none":
                continue
            sgui(f"{p}_{kind}_{rid}", f"\tis_shown = {{ {p}_{kind}_{rid} = yes }}\n")
        sgui(f"{p}_snoozed_{rid}", f"\tis_shown = {{ has_variable = {p}_snooze_{rid} }}\n")
        sgui(f"{p}_snooze_{rid}",
             f"\teffect = {{\n\t\tset_variable = {{ name = {p}_snooze_{rid} value = yes days = {days} }}\n\t}}\n")
        sgui(f"{p}_wake_{rid}", f"\teffect = {{\n\t\tremove_variable = {p}_snooze_{rid}\n\t}}\n")
    return "\n".join(out)


def _script_values(p):
    return (HEADER_COMMENT +
            "# State scope: infrastructure left over after what the state's buildings use (negative = shortfall).\n"
            f"{p}_infrastructure_balance = {{\n\tvalue = infrastructure\n\tsubtract = infrastructure_usage\n}}\n")


def _alert_panel(rule, targets):
    """The alert's open_panel value (panel|tab), or None when the rule has no screen or a custom opener."""
    if rule["target"] == "none":
        return None
    t = targets[rule["target"]]
    if "panel" not in rule and "alert_panel" in t:
        return t["alert_panel"] or None
    panel = rule.get("panel", t.get("panel"))
    if not panel:
        return None
    tab = rule.get("tab", t.get("tab"))
    return f"{panel}|{tab}" if tab else panel


def _alert_types(p, rules, targets):
    out = [HEADER_COMMENT]
    for rule in rules:
        panel = _alert_panel(rule, targets)
        open_line = f"\topen_panel = {panel}\n" if panel else ""
        out.append(
            f"{p}_{rule['id']} = {{\n"
            f"\tscript_context = player_country\n"
            f"\ttexture = \"gfx/interface/{p}/alert.dds\"\n"
            f"\tvalid = {{\n\t\t{p}_next_{rule['id']} = yes\n\t}}\n"
            f"{open_line}"
            f"\ttype = important_action\n"
            f"\tcolor = yellow\n"
            f"}}\n"
        )
    return "\n".join(out)


# --------------------------------------------------------------------------- GUI helpers

class Node:
    """A Jomini GUI element: `kind = { props... children... }`."""

    def __init__(self, kind, *items, **props):
        self.kind, self.items = kind, [i for i in items if i is not None]
        self.props = props

    def render(self, depth=0):
        pad = "\t" * (depth + 1)
        lines = [f"{chr(9) * depth}{self.kind} = {{"]
        # `using = template` lines go first, so the element's own properties override the template's.
        lines += [pad + i for i in self.items if isinstance(i, str) and i.startswith("using")]
        for key, value in self.props.items():
            key = key.rstrip("_")  # onclick_ → onclick (several onclick lines)
            for v in value if isinstance(value, list) else [value]:
                lines.append(f"{pad}{key} = {_fmt(key, v)}")
        for item in self.items:
            if isinstance(item, Node):
                lines.append(item.render(depth + 1))
            elif not item.startswith("using"):
                lines.append(pad + item)
        lines.append(f"{chr(9) * depth}}}")
        return "\n".join(lines)


# Properties whose values are keywords, written bare as vanilla does; every other string is quoted.
BARE_PROPS = {"align", "parentanchor", "widgetanchor", "filter_mouse", "elide"}


def _fmt(key, v):
    if isinstance(v, tuple):
        return "{ " + " ".join(str(x) for x in v) + " }"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return str(v)
    return v if key in BARE_PROPS else f'"{v}"'


def _scope():
    return "GuiScope.SetRoot(GetPlayer.MakeScope).End"


def _shown(p, kind, rid=None):
    name = f"{p}_{kind}_{rid}" if rid else f"{p}_{kind}"
    return f"GetScriptedGui('{name}').IsShown({_scope()})"


def _execute(p, kind, rid):
    return f"[GetScriptedGui('{p}_{kind}_{rid}').Execute({_scope()})]"


def _var(name):
    return f"GetVariableSystem.Exists('{name}')"


def _has(name, value):
    return f"GetVariableSystem.HasValue('{name}', '{value}')"


def _and(*terms):
    out = terms[-1]
    for term in reversed(terms[:-1]):
        out = f"And({term}, {out})"
    return out


def _or(*terms):
    out = terms[-1]
    for term in reversed(terms[:-1]):
        out = f"Or({term}, {out})"
    return out


def _bind(expr):
    return f"[{expr}]"


def _open_guide(rid):
    return [f"[GetVariableSystem.Set('npa_guide', '{rid}')]", "[GetVariableSystem.Set('npa_step', '1')]"]


def _tex(p, name):
    return f"gfx/interface/{p}/{name}.dds"


def _text(text, x, y, w, h, size=16, align="left|nobaseline", fmt=None, multiline=False):
    props = dict(text=text, position=(x, y), size=(w, h), fontsize=size, align=align, alwaystransparent=True)
    if fmt:
        props["default_format"] = fmt
    if multiline:
        props["multiline"] = True
    else:
        props["elide"] = "right"
    return Node("textbox", "using = regular_font", **props)


def _text_button(p, name, x, y, w, h, label, onclick, tooltip=None, visible=None, texture="text_button"):
    props = dict(name=name, position=(x, y), size=(w, h), texture=_tex(p, texture), onclick_=onclick)
    if tooltip:
        props["tooltip"] = tooltip
    if visible:
        props["visible"] = _bind(visible)
    return Node("button", _text(label, 0, 0, w, h, size=15, align="center|nobaseline"), **props)


def _icon(p, name, x, y, w, h, texture, visible=None):
    props = dict(name=name, position=(x, y), size=(w, h), texture=_tex(p, texture), alwaystransparent=True)
    if visible:
        props["visible"] = _bind(visible)
    return Node("icon", **props)


def _pulse(name, x, y, w, h, texture, visible):
    """A glow frame that fades in and out forever while visible."""
    return Node(
        "widget",
        Node("icon", size=("100%", "100%"), texture=texture, alwaystransparent=True),
        "state = { name = _show next = npa_fade alpha = 1 }",
        "state = { name = npa_fade next = npa_glow duration = 0.5 alpha = 0.25 }",
        "state = { name = npa_glow next = npa_fade duration = 0.7 alpha = 1 }",
        name=name, position=(x, y), size=(w, h), alwaystransparent=True, visible=_bind(visible),
    )


def _open_command(rule, t):
    if "open" in t and "panel" not in rule:
        return t["open"]
    panel = rule.get("panel", t.get("panel"))
    tab = rule.get("tab", t.get("tab", "default"))
    # DontToggle: step 1 of a guide usually has the player open that panel already; plain OpenPanelTab would close it.
    return f"[InformationPanelBar.OpenPanelTabDontToggle('{panel}', '{tab}')]"


# --------------------------------------------------------------------------- HUD layer

def _hud_gui(config, by_target):
    mod, targets, toggle, nxt = config["mod"], config["targets"], config["toggle"], config["next"]
    p, rules = mod["prefix"], config["rule"]
    show_all = _var("npa_show_all")
    items = []

    # Advisor button, with a small "!" while any advice is active.
    items.append(Node(
        "button",
        _icon(p, f"{p}_toggle_alert", TOGGLE_SIZE - ALERT_DOT + 4, -4, ALERT_DOT, ALERT_DOT, "badge_small",
              visible=_shown(p, "any_active")),
        name=f"{p}_toggle_button", position=(toggle["x"], toggle["y"]), size=(TOGGLE_SIZE, TOGGLE_SIZE),
        texture=_tex(p, "advisor_button"), tooltip=f"{p}_toggle_tt",
        onclick_=["[GetVariableSystem.Toggle('npa_panel')]", "[GetVariableSystem.Clear('npa_guide')]"],
    ))

    # "Do this next" bar: one button per rule; only the next move's is visible.
    bar = [Node(
        "button",
        _text(f"{p}_{r['id']}_next", 18, 0, NEXT_W - 26, NEXT_H, size=15),
        name=f"{p}_next_{r['id']}", size=(NEXT_W, NEXT_H), texture=_tex(p, "next_bar"),
        visible=_bind(_shown(p, "next", r["id"])), tooltip=f"{p}_{r['id']}_next_tt",
        onclick_=_open_guide(r["id"]), onrightclick=_execute(p, "snooze", r["id"]),
    ) for r in rules]
    items.append(Node(
        "widget", *bar,
        name=f"{p}_next_bar", position=(nxt["x"], nxt["y"]), size=(NEXT_W, NEXT_H),
        # Hidden while a vanilla side panel is open: the bar would sit over its header.
        visible=_bind(_and(f"Not({_var('npa_panel')})", f"Not({_var('npa_guide')})",
                           f"Not({_var('npa_hide_next')})", "Not(InformationPanelBar.IsAnyPanelOpen)")),
    ))

    # Per button: one highlight frame (its rule is the next move, or its guide is open) and the badges.
    for target, target_rules in by_target.items():
        t = targets[target]
        items.append(_pulse(
            f"{p}_pulse_{target}", t["x"] - GLOW_PAD, t["y"] - GLOW_PAD, t["w"] + 2 * GLOW_PAD,
            t["h"] + 2 * GLOW_PAD, _tex(p, "glow"),
            _or(show_all, _shown(p, "target_next", target), *(_has("npa_guide", r["id"]) for r in target_rules)),
        ))
        bx, by = t["x"] + t["w"] - BADGE + 4, t["y"] - 4
        for r in target_rules:
            items.append(Node(
                "button",
                name=f"{p}_badge_{r['id']}", position=(bx, by), size=(BADGE, BADGE), texture=_tex(p, "badge"),
                visible=_bind(_or(show_all, _shown(p, "show", r["id"]))), tooltip=f"{p}_{r['id']}_tt",
                onclick_=_open_guide(r["id"]), onrightclick=_execute(p, "snooze", r["id"]),
            ))

    root = Node("widget", *items, name=f"{p}_hud_root", size=("100%", "100%"), layer="layer_ingame_hud",
                visible=ROOT_VISIBLE)
    return HEADER_COMMENT + root.render() + "\n"


# --------------------------------------------------------------------------- menu layer: panel and guide

def _panel_layout(by_category):
    n_tabs = len(by_category)
    width = GAP + COLUMNS * (CARD_W + GAP)
    tab_w = (width - 2 * GAP - (n_tabs - 1) * TAB_GAP) // n_tabs
    banner_y = HEADER_H + 8
    tabs_y = banner_y + BANNER_H + 8
    cards_y = tabs_y + TAB_H + 10
    rows = math.ceil(max(len(r) for r in by_category.values()) / COLUMNS)
    height = cards_y + rows * (CARD_H + GAP) + FOOTER_H
    cards = {}
    for cat_rules in by_category.values():
        for i, rule in enumerate(cat_rules):
            cards[rule["id"]] = (GAP + (i % COLUMNS) * (CARD_W + GAP), cards_y + (i // COLUMNS) * (CARD_H + GAP))
    tabs = {cat: (GAP + k * (tab_w + TAB_GAP), tabs_y) for k, cat in enumerate(by_category)}
    return {"width": width, "height": height, "cards": cards, "tabs": tabs, "tab_w": tab_w, "banner_y": banner_y}


def _blocker(**props):
    """A window that keeps clicks from reaching the map behind it."""
    return dict(alwaystransparent=False, filter_mouse="left|right", **props)


def _windows_gui(config, by_category, layout):
    mod, targets, guide = config["mod"], config["targets"], config["guide"]
    p, rules = mod["prefix"], config["rule"]
    categories = list(by_category)
    w, h = layout["width"], layout["height"]

    # ---- panel
    items = [_icon(p, f"{p}_panel_bg", 0, 0, w, h, "panel_bg"),
             _text(f"{p}_panel_title", 18, 8, w - 80, 26, size=20, fmt="#header"),
             _text(f"{p}_panel_subtitle", 18, 31, w - 80, 18, size=14),
             Node("button", name=f"{p}_close_button", position=(w - 36, 12), size=(24, 24),
                  texture=_tex(p, "close_button"), tooltip=f"{p}_close_tt",
                  onclick="[GetVariableSystem.Clear('npa_panel')]")]
    bx, by, bw = GAP, layout["banner_y"], w - 2 * GAP
    for r in rules:
        items.append(Node(
            "button",
            _text(f"{p}_{r['id']}_banner", 18, 0, bw - 26, BANNER_H, size=16),
            name=f"{p}_banner_{r['id']}", position=(bx, by), size=(bw, BANNER_H), texture=_tex(p, "banner"),
            visible=_bind(_shown(p, "next", r["id"])), tooltip=f"{p}_{r['id']}_next_tt",
            onclick_=[*_open_guide(r["id"]), "[GetVariableSystem.Clear('npa_panel')]"],
        ))
    items.append(Node("widget", _icon(p, f"{p}_banner_none_bg", 0, 0, bw, BANNER_H, "banner"),
                      _text(f"{p}_banner_none", 18, 0, bw - 26, BANNER_H, size=16),
                      name=f"{p}_banner_none", position=(bx, by), size=(bw, BANNER_H),
                      visible=_bind(f"Not({_shown(p, 'any_active')})")))
    for k, (cat, (tx, ty)) in enumerate(layout["tabs"].items()):
        selected = _has("npa_tab", cat) if k else _or(_has("npa_tab", cat), f"Not({_var('npa_tab')})")
        items.append(_text_button(p, f"{p}_tab_{cat}", tx, ty, layout["tab_w"], TAB_H, f"{p}_tab_{cat}",
                                  f"[GetVariableSystem.Set('npa_tab', '{cat}')]", texture="tab"))
        items.append(_icon(p, f"{p}_tab_{cat}_active", tx, ty, layout["tab_w"], TAB_H, "tab_active",
                           visible=selected))
    for cat_index, cat in enumerate(categories):
        on_tab = _has("npa_tab", cat) if cat_index else _or(_has("npa_tab", cat), f"Not({_var('npa_tab')})")
        for r in by_category[cat]:
            rid = r["id"]
            cx, cy = layout["cards"][rid]
            ix, iy, tx = 10, (CARD_H - PANEL_BADGE) // 2, 20 + PANEL_BADGE
            active, snoozed = _shown(p, "rule", rid), _shown(p, "snoozed", rid)
            items.append(Node(
                "widget",
                Node("button", name=f"{p}_card_{rid}_button", size=(CARD_W, CARD_H), texture=_tex(p, "card"),
                     tooltip=f"{p}_{rid}_card_tt",
                     onclick_=[*_open_guide(rid), "[GetVariableSystem.Clear('npa_panel')]"]),
                Node("button", name=f"{p}_row_{rid}_active", position=(ix, iy), size=(PANEL_BADGE, PANEL_BADGE),
                     texture=_tex(p, "badge_panel"), tooltip=f"{p}_{rid}_row_tt", visible=_bind(active),
                     onclick_=[*_open_guide(rid), "[GetVariableSystem.Clear('npa_panel')]"],
                     onrightclick=_execute(p, "snooze", rid)),
                Node("button", name=f"{p}_row_{rid}_snoozed", position=(ix, iy), size=(PANEL_BADGE, PANEL_BADGE),
                     texture=_tex(p, "snoozed"), tooltip=f"{p}_{rid}_snoozed_tt", visible=_bind(snoozed),
                     onclick=_execute(p, "wake", rid)),
                _icon(p, f"{p}_row_{rid}_ok", ix, iy, PANEL_BADGE, PANEL_BADGE, "ok",
                      visible=_and(f"Not({active})", f"Not({snoozed})")),
                _text(f"{p}_{rid}_title", tx, 8, CARD_W - tx - 10, 22, size=17, fmt="#header"),
                _text(f"{p}_{rid}_desc", tx, 30, CARD_W - tx - 10, 40, size=14, multiline=True),
                name=f"{p}_card_{rid}", position=(cx, cy), size=(CARD_W, CARD_H), visible=_bind(on_tab),
            ))
    fy = h - FOOTER_H + (FOOTER_H - FOOTER_BUTTON_H) // 2
    items.append(_text_button(p, f"{p}_debug_button", GAP + 2, fy, FOOTER_BUTTON_W, FOOTER_BUTTON_H,
                              f"{p}_debug_label", "[GetVariableSystem.Toggle('npa_show_all')]", f"{p}_debug_tt"))
    items.append(_text_button(p, f"{p}_hide_next_button", GAP + FOOTER_BUTTON_W + 12, fy, FOOTER_BUTTON_W,
                              FOOTER_BUTTON_H, f"{p}_hide_next_label", "[GetVariableSystem.Toggle('npa_hide_next')]",
                              f"{p}_hide_next_tt"))
    hint_x = GAP + 2 * (FOOTER_BUTTON_W + 12) + 6
    items.append(_text(f"{p}_footer_hint", hint_x, fy, w - hint_x - GAP, FOOTER_BUTTON_H, size=14))
    panel = Node("widget", *items, name=f"{p}_panel", parentanchor="center", widgetanchor="center", size=(w, h),
                 visible=_bind(_var("npa_panel")), **_blocker())

    # ---- guide: one page per rule and step
    pages = []
    text_w = GUIDE_W - 2 * (STEP_BOX[0] + 12)
    gy = GUIDE_H - 12 - GUIDE_BUTTON_H
    gx = [14 + i * (GUIDE_BUTTON_W + GUIDE_BUTTON_GAP) for i in range(4)]
    for r in rules:
        rid, n = r["id"], len(r["steps"])
        for s in range(1, n + 1):
            page = [_text(f"{p}_{rid}_title", 18, 8, GUIDE_W - 80, 26, size=20, fmt="#header"),
                    _text(f"{p}_{rid}_step_{s}", STEP_BOX[0] + 12, STEP_BOX[1] + 10, text_w,
                          STEP_BOX[3] - STEP_BOX[1] - 16, size=17, multiline=True),
                    _text(f"{p}_{rid}_why_text", WHY_BOX[0] + 12, WHY_BOX[1] + 10, text_w,
                          WHY_BOX[3] - WHY_BOX[1] - 16, size=15, multiline=True)]
            if s > 1:
                page.append(_text_button(p, f"{p}_guide_{rid}_{s}_back", gx[0], gy, GUIDE_BUTTON_W, GUIDE_BUTTON_H,
                                         f"{p}_guide_back", f"[GetVariableSystem.Set('npa_step', '{s - 1}')]",
                                         texture="guide_button"))
            if r["target"] != "none":
                page.append(_text_button(p, f"{p}_guide_{rid}_{s}_open", gx[1], gy,
                                         GUIDE_BUTTON_W, GUIDE_BUTTON_H, f"{p}_guide_open",
                                         _open_command(r, targets[r["target"]]), f"{p}_{rid}_open_tt",
                                         texture="guide_button"))
            page.append(_text_button(p, f"{p}_guide_{rid}_{s}_all", gx[2], gy,
                                     GUIDE_BUTTON_W, GUIDE_BUTTON_H, f"{p}_guide_all",
                                     ["[GetVariableSystem.Clear('npa_guide')]",
                                      "[GetVariableSystem.Set('npa_panel', 'yes')]"], texture="guide_button"))
            if s < n:
                page.append(_text_button(p, f"{p}_guide_{rid}_{s}_next", gx[3], gy,
                                         GUIDE_BUTTON_W, GUIDE_BUTTON_H, f"{p}_guide_next",
                                         f"[GetVariableSystem.Set('npa_step', '{s + 1}')]", texture="guide_button"))
            else:
                page.append(_text_button(p, f"{p}_guide_{rid}_{s}_done", gx[3], gy,
                                         GUIDE_BUTTON_W, GUIDE_BUTTON_H, f"{p}_guide_done",
                                         "[GetVariableSystem.Clear('npa_guide')]", texture="guide_button"))
            pages.append(Node("widget", *page, name=f"{p}_guide_{rid}_{s}", size=(GUIDE_W, GUIDE_H),
                              visible=_bind(_and(_has("npa_guide", rid), _has("npa_step", s)))))
    guide_window = Node(
        "widget",
        _icon(p, f"{p}_guide_bg", 0, 0, GUIDE_W, GUIDE_H, "guide_bg"),
        _text(f"{p}_guide_subtitle", 18, 33, GUIDE_W - 80, 18, size=14),
        Node("button", name=f"{p}_guide_close", position=(GUIDE_W - 36, 12), size=(24, 24),
             texture=_tex(p, "close_button"), tooltip=f"{p}_close_tt",
             onclick="[GetVariableSystem.Clear('npa_guide')]"),
        *pages,
        name=f"{p}_guide", parentanchor="top|right", widgetanchor="top|right", position=(guide["x"], guide["y"]),
        size=(GUIDE_W, GUIDE_H),
        visible=_bind(_var("npa_guide")), **_blocker(),
    )

    root = Node("widget", panel, guide_window, name=f"{p}_windows_root", size=("100%", "100%"),
                layer=WINDOWS_LAYER, visible=ROOT_VISIBLE)
    return HEADER_COMMENT + root.render() + "\n"


# --------------------------------------------------------------------------- textures

def _textures(out_dir, config, layout):
    canvases = {
        "badge": art.advice_badge(BADGE),
        "badge_small": art.advice_badge(ALERT_DOT),
        "badge_panel": art.advice_badge(PANEL_BADGE),
        "alert": art.advice_badge(64),
        "ok": art.ok_badge(PANEL_BADGE),
        "snoozed": art.snoozed_badge(PANEL_BADGE),
        "advisor_button": art.advisor_button(TOGGLE_SIZE),
        "close_button": art.close_button(24),
        "text_button": art.text_button(FOOTER_BUTTON_W, FOOTER_BUTTON_H),
        "panel_bg": art.panel_background(layout["width"], layout["height"], HEADER_H),
        "card": art.card(CARD_W, CARD_H),
        "tab": art.text_button(layout["tab_w"], TAB_H),
        "tab_active": art.tab_highlight(layout["tab_w"], TAB_H),
        "guide_bg": art.panel_background(GUIDE_W, GUIDE_H, GUIDE_HEADER, boxes=(STEP_BOX, WHY_BOX)),
        "guide_button": art.text_button(GUIDE_BUTTON_W, GUIDE_BUTTON_H),
        "banner": art.banner(layout["width"] - 2 * GAP, BANNER_H),
        "next_bar": art.banner(NEXT_W, NEXT_H),
        "glow": art.glow_frame(64, 64, inset=GLOW_PAD),
    }
    for name, canvas in canvases.items():
        write_dds(os.path.join(out_dir, name + ".dds"), canvas.width, canvas.height, canvas.pixels)


# --------------------------------------------------------------------------- localization & metadata

def _localizations(mod, rules, targets, categories, locales):
    """Returns {relative path: file text} for every Victoria 3 language."""
    validate_locales("vic3", locales, LANGUAGES, rules, targets, categories, UI_KEYS)
    english = locales["english"]
    return {f"localization/{lang}/{mod['prefix']}_advisor_l_{lang}.yml":
            _localization(lang, mod, rules, targets, categories, english, locales.get(lang, {}))
            for lang in LANGUAGES}


def _localization(lang, mod, rules, targets, categories, english, loc):
    p, days = mod["prefix"], mod["snooze_days"]
    ui = {**english["ui"], **loc.get("ui", {})}

    def fmt(key, **kw):
        return ui[key].format(days=days, **kw)

    entries = {f"{p}_{key}": fmt(key) for key in GUI_TEXT_KEYS}
    for cat, label in categories.items():
        entries[f"{p}_tab_{cat}"] = loc.get("categories", {}).get(cat, label)
    for rule in rules:
        rid = rule["id"]
        text = rule_text(rule, loc)
        if rule["target"] == "none":
            label = fmt("none_label")
        else:
            label = loc.get("targets", {}).get(rule["target"], targets[rule["target"]]["label"])
        body = f"#header {text['title']}#!\n{text['advice']}\n\n{text['why']}"
        entries[f"{p}_{rid}_title"] = text["title"]
        entries[f"{p}_{rid}_desc"] = f"{text['advice']} {fmt('desc_where', label=label)}"
        entries[f"{p}_{rid}_tt"] = f"{body}\n\n{fmt('badge_hint', label=label)}"
        entries[f"{p}_{rid}_row_tt"] = f"{body}\n\n{fmt('row_hint')}"
        entries[f"{p}_{rid}_card_tt"] = f"#header {text['title']}#!\n{text['advice']}\n\n{fmt('card_tt')}"
        entries[f"{p}_{rid}_snoozed_tt"] = fmt("snoozed_tt", title=text["title"])
        entries[f"{p}_{rid}_next"] = f"#v {fmt('next_prefix')}#! {text['title']}"
        entries[f"{p}_{rid}_banner"] = f"#v {fmt('next_prefix')}#! {text['title']}  {fmt('desc_where', label=label)}"
        entries[f"{p}_{rid}_next_tt"] = f"{body}\n\n{fmt('next_hint', label=label)}"
        entries[f"{p}_{rid}_open_tt"] = fmt("guide_open_tt", label=label)
        total = len(text["steps"])
        for n, step in enumerate(text["steps"], 1):
            entries[f"{p}_{rid}_step_{n}"] = f"#v {fmt('guide_step', n=n, total=total)}#!\n\n{step}"
        entries[f"{p}_{rid}_why_text"] = f"#v {fmt('guide_why')}#!\n{text['why']}"
        # Native alert (Important Actions list) while this rule is "Do this next".
        entries[f"alert_{p}_{rid}_name"] = f"{fmt('alert_prefix')} {text['title']}"
        entries[f"alert_{p}_{rid}_desc"] = f"{text['advice']}\n\n{text['why']}"
        entries[f"alert_{p}_{rid}_hint"] = text["steps"][0]
        entries[f"alert_{p}_{rid}_action"] = fmt("alert_action", label=label)
        entries[f"{p}_{rid}_setting_name"] = f"{fmt('alert_prefix')} {text['title']}"
    lines = [f"l_{lang}:"] + [f' {key}: "{value.strip()}"'.replace("\n", "\\n") for key, value in entries.items()]
    return "\n".join(lines) + "\n"


def _metadata(mod):
    return json.dumps({
        "name": mod["name"],
        "id": mod["id"],
        "version": mod["version"],
        "game_id": "victoria3",
        "supported_game_version": mod["supported_version"],
        "short_description": mod["description"],
        "tags": mod.get("tags", ["Utilities"]),
        "relationships": [],
        "game_custom_data": {"multiplayer_synchronized": True},
    }, indent=2, ensure_ascii=False) + "\n"
