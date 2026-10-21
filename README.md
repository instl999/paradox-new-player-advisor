# New Player Advisor (HOI4 · Victoria 3 planned)

An in-game advisor for new players, in the style of Civilization VI's advisor. It doesn't pop up alerts. Instead, a small
gold **!** badge appears on the topbar button where your best move is right now: the Construction button early on
("build civilian factories"), Politics once war is coming ("mobilise your economy"), and so on.

- **Hover** over a badge to see the advice and the reason for it.
- **Left-click** a badge, or the lightbulb button, to open the Advisor panel. It is a checklist of every recommendation
  and its state: gold = do this, green = fine, grey = snoozed.
- **Right-click** a badge to snooze that advice for 30 days.

## How it works

All the advice is written in one data file, [rules/hoi4.toml](rules/hoi4.toml). Each rule is a HOI4 trigger plus some
text. `tools/build.py` turns the rules into a normal HOI4 mod:

| Generated file | Purpose |
|---|---|
| `common/scripted_triggers/npa_advisor_triggers.txt` | One trigger per rule (`npa_rule_<id>`), plus "show the badge only if no higher-priority rule on the same button is active" |
| `common/scripted_guis/npa_advisor_scripted_guis.txt` | Visibility and click logic for the badges and the panel (player-country scope) |
| `interface/npa_advisor.gui` / `.gfx` | One badge-sized window per topbar button, the lightbulb button, and the panel |
| `gfx/interface/npa/*.dds` | Icons, drawn by `tools/art.py`, so no image editor is needed |
| `localisation/english/*.yml` | Titles, advice and tooltips (written with the UTF-8 BOM HOI4 requires) |

Each badge sits in its own tiny window, so it never covers the vanilla button underneath it.

## Build & install

Requires Python 3.11+ and no other packages.

```bash
python tools/build.py hoi4 --install
```

This builds into `build/hoi4/` and copies the mod to `Documents/Paradox Interactive/Hearts of Iron IV/mod/`. Then enable
**New Player Advisor** in a playset in the Paradox launcher. (If your Documents folder is somewhere else, add
`--game-dir "<path to the Hearts of Iron IV user folder>"`.)

To install on another PC (no Python needed there), make an installer zip:

```bash
python tools/build.py hoi4 --package
```

This creates `dist/new_player_advisor-hoi4-<version>.zip`. Unzip it on the gaming PC and double-click **Install.bat**
(**Uninstall.bat** removes it).

Like any mod, it changes the game checksum, so **Ironman achievements are disabled** while it is enabled.

## Calibrating badge positions (first run)

The badge coordinates in `rules/hoi4.toml` (`[targets.*]` and `[toggle]`) are estimates. They have not been checked in
the game yet, and they can shift between patches and UI scales. To line them up:

1. Start the game with the `-debug` launch option, so HOI4 reloads changed `.gui` files while it runs.
2. Open the Advisor (lightbulb) and click **Show all icons**. Every badge now shows at once.
3. Edit the `x` / `y` values in `Documents/.../mod/new_player_advisor/interface/npa_advisor.gui` and watch them move.
   Aim for the top-right corner of each button.
4. Copy the final numbers into `rules/hoi4.toml` so the next build keeps them.

If the badges don't appear at all, set `parent_window_token = ""` in the rules file. This switches to absolute screen
coordinates (the topbar sits at the top-left of the screen, so the numbers are similar).

Check `Documents/.../Hearts of Iron IV/logs/error.log` after loading. If a trigger or GUI property has been renamed in
the current patch, it shows up there.

## Adding advice

Add a `[[rule]]` to `rules/hoi4.toml`:

```toml
[[rule]]
id = "research_more"            # lowercase, unique
category = "economy"            # panel tab: one of [categories] (max 10 rules per tab)
target = "research"             # one of the [targets.*] buttons, or "none" for panel-only advice
priority = 10                   # lower wins when several rules point at the same button
dlc = "lar"                     # optional: a key from [dlc]; hidden for players without that DLC
title = "Short headline"
advice = "One sentence: what to do. Shown in the panel."
why = "Two or three sentences: why it matters. Shown in the tooltip and under the guide."
steps = [                       # 1-6 steps, shown one at a time in the guide window
  "Click the Research button in the topbar.",
  "...",
]
trigger = '''
has_war = no
amount_research_slots < 3
'''
```

Add the translation under `[rules.<id>]` in `rules/locale/hoi4/simp_chinese.toml`. It needs the same number of steps.
Then rebuild. The build rejects duplicate IDs, unknown targets, categories or DLC keys, mismatched step counts,
unbalanced braces, and double quotes in text.

The guide is driven by two country variables: `npa_guide` (which rule's guide is open) and `npa_step`. Each step is
its own text box, shown only while it is the current step.

## Languages

HOI4 only loads text for the language the game is running in, and never falls back to English. So the build writes a
file for every HOI4 language. The texts come from `rules/locale/hoi4/<language>.toml`:

- `english.toml` holds the interface text. The English advice text itself lives in `rules/hoi4.toml`.
- `simp_chinese.toml` is a full Simplified Chinese translation.
- To add a language, copy `simp_chinese.toml` to `german.toml`, `french.toml`, etc. and translate it. Anything left
  out shows in English.

## Download

Players can get the ready-made installer from the
[Releases page](https://github.com/instl999/paradox-new-player-advisor/releases/latest): download the zip, unzip it,
and double-click **Install.bat**. Python is not needed.

## License

[MIT](LICENSE). You are free to use, change and share this mod; keep the copyright notice.

## Roadmap

- **Victoria 3 output step.** It will use the same rule format, with Vic3 triggers and its own GUI system (Vic3 uses
  `.gui` templates with data-bound visibility, not HOI4's scripted GUIs). Planned first rules: construction queue
  idle, budget deficit, goods shortages, legitimacy, and law changes that interest groups support.
- More HOI4 rules: naval and air production, the logistics screen (supply/railways), decisions, and focus-specific
  hints for the major nations.
- Translations (add `localisation/<language>/` output).
