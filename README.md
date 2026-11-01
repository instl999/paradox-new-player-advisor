# New Player Advisor (Hearts of Iron IV · Victoria 3)

An in-game advisor for new players, in the style of Civilization VI's advisor. It doesn't pop up alerts. Instead, a small
gold **!** badge appears on the button where your best move is right now. In HOI4 that is a topbar button: Construction
early on ("build civilian factories"), Politics once war is coming ("mobilise your economy"). In Victoria 3 it is a
left sidebar button: Budget when you are losing money, Buildings when construction sits idle, and so on.

- **Do this next:** a bar beside the lightbulb always names the single most useful move right now, and that move's
  button **pulses**. Click the bar for a step-by-step guide.
- **Hover** over a badge to see the advice and the reason for it.
- **Left-click** a badge, or the lightbulb button, to open the Advisor panel. It is a checklist of every recommendation
  and its state: gold = do this, green = fine, grey = snoozed.
- **Right-click** a badge to snooze that advice for 30 days.
- **Victoria 3 only:** the guide has an **Open screen** button, and the current "Do this next" also appears in the
  game's own Important Actions list.

| Game | Version | Rules | Status |
|---|---|---|---|
| Hearts of Iron IV | 0.3.0 | 31 | Released 0.2.0; 0.3.0 adds the next-move bar, pulse highlight and global priorities |
| Victoria 3 (patch 1.15) | 0.1.0 | 20 | New; passes all automated checks, not yet tested in the game |

## How it works

All the advice is written in one data file per game: [rules/hoi4.toml](rules/hoi4.toml) and
[rules/vic3.toml](rules/vic3.toml). Each rule is a game trigger plus some text. `tools/build.py` turns the rules into a
normal mod. For HOI4:

| Generated file | Purpose |
|---|---|
| `common/scripted_triggers/npa_advisor_triggers.txt` | One trigger per rule (`npa_rule_<id>`), "show the badge only if no higher-priority rule on the same button is active" (`npa_show_<id>`), and "this is the next move" (`npa_next_<id>`) |
| `common/scripted_guis/npa_advisor_scripted_guis.txt` | Visibility and click logic for the badges and the panel (player-country scope) |
| `interface/npa_advisor.gui` / `.gfx` | One badge-sized window per topbar button, the lightbulb button, and the panel |
| `gfx/interface/npa/*.dds` | Icons, drawn by `tools/art.py`, so no image editor is needed |
| `localisation/english/*.yml` | Titles, advice and tooltips (written with the UTF-8 BOM HOI4 requires) |

Each badge sits in its own tiny window, so it never covers the vanilla button underneath it. The guide is driven by
two country variables: `npa_guide` (which rule's guide is open) and `npa_step`. Each step is its own text box, shown
only while it is the current step.

The Victoria 3 mod adds its two windows through `gui/scripted_widgets`, so it overrides **no vanilla files** and works
alongside other UI mods. See [docs/DESIGN.md §6](docs/DESIGN.md) for its files.

The full design (requirements, architecture, priority bands, risks) is in [docs/DESIGN.md](docs/DESIGN.md). The
in-game test checklist is [docs/TESTING.md](docs/TESTING.md).

## Build & install

Requires Python 3.11+ and no other packages.

```bash
python tools/build.py hoi4 --install
```

```bash
python tools/build.py vic3 --install
```

This builds into `build/<game>/` and copies the mod to `Documents/Paradox Interactive/<game>/mod/`. Then enable
**New Player Advisor** in a playset in the Paradox launcher. (If your Documents folder is somewhere else, add
`--game-dir "<path to the game's user folder>"`.)

To install on another PC (no Python needed there), make an installer zip:

```bash
python tools/build.py hoi4 --package
```

This creates `dist/new_player_advisor-hoi4-<version>.zip` (or `-vic3-` for Victoria 3). Unzip it on the gaming PC and double-click **Install.bat**
(**Uninstall.bat** removes it).

Like any mod, it changes the game checksum, so **Ironman achievements are disabled** while it is enabled.

## Previewing the Victoria 3 interface

```bash
python tools/preview.py vic3
```

This renders the advisor's Victoria 3 interface to `build/vic3/preview/index.html`: the HUD, the panel and a guide,
with the real textures and text, for a sample situation. Use `--lang simp_chinese` for the Chinese text.

## Calibrating badge positions (first run)

In Victoria 3, the badge boxes are in `rules/vic3.toml` → `[targets.*]` (`x`, `y`, `w`, `h` of each sidebar button).
Open the Advisor, click **Show all icons**, and adjust them the same way as below. With the `-debug_mode` launch
option, Victoria 3 reloads changed `.gui` files while it runs, like HOI4 with `-debug`.

The HOI4 badge coordinates in `rules/hoi4.toml` (`[targets.*]` and `[toggle]`) are estimates. They have not been checked in
the game yet, and they can shift between patches and UI scales. To line them up:

1. Start the game with the `-debug` launch option, so HOI4 reloads changed `.gui` files while it runs.
2. Open the Advisor (lightbulb) and click **Show all icons**. Every badge now shows at once.
3. Edit the `x` / `y` values in `Documents/.../mod/new_player_advisor/interface/npa_advisor.gui` and watch them move.
   Aim for the top-right corner of each button.
4. Copy the final numbers into `rules/hoi4.toml` so the next build keeps them.

If the badges don't appear at all, set `parent_window_token = ""` in the rules file. This switches to absolute screen
coordinates (the topbar sits at the top-left of the screen, so the numbers are similar).

Check `Documents/.../Hearts of Iron IV/logs/error.log` after loading. If a trigger or GUI property has been renamed in
the current patch, it shows up there (Victoria 3: `Documents/.../Victoria 3/logs/error.log`).

## Adding advice

Add a `[[rule]]` to `rules/hoi4.toml`:

```toml
[[rule]]
id = "research_more"            # lowercase, unique
category = "economy"            # panel tab: one of [categories] (max 10 rules per tab)
target = "research"             # one of the [targets.*] buttons, or "none" for panel-only advice
priority = 25                   # global order, lower = more important (bands: docs/DESIGN.md §4.2)
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

Victoria 3 rules use the same format in `rules/vic3.toml`; their text may not contain `[ ] $ #`, which mean something
in Victoria 3 localization. Optional `panel` / `tab` fields choose the screen the guide's **Open screen** button opens.

Add the translation under `[rules.<id>]` in `rules/locale/<game>/simp_chinese.toml`. It needs the same number of steps.
Then rebuild. The build rejects duplicate IDs, unknown targets, categories or DLC keys, mismatched step counts,
unbalanced braces, and double quotes in text.

It also rejects trigger names that are not in [rules/known/hoi4_triggers.txt](rules/known/hoi4_triggers.txt) (or
[vic3_triggers.txt](rules/known/vic3_triggers.txt)). The
game would only log a misspelled trigger in error.log and treat it as false, so the rule would never fire. If you
use a trigger that isn't listed yet, check it on the [wiki](https://hoi4.paradoxwikis.com/Triggers) and add it with
its source. The Victoria 3 list was checked against the game's own 1.15 script documentation.

## Tests

```bash
python -m unittest discover tests
```

The tests build both mods into a temporary folder and check them the way the game would: every scripted-GUI element
or scripted GUI exists, every text key exists in every language, every sprite and texture is valid, every data-binding
expression is well formed, and bad rules files are rejected. They don't need the game. The in-game checklist is
[docs/TESTING.md](docs/TESTING.md).

## Languages

The games only load text for the language they run in, and may not fall back to English. So the build writes a file
for every language the game supports (10 for HOI4, 11 for Victoria 3). The texts come from
`rules/locale/<game>/<language>.toml`:

- `english.toml` holds the interface text. The English advice text itself lives in `rules/<game>.toml`.
- `simp_chinese.toml` is a full Simplified Chinese translation, for both games.
- To add a language, copy `simp_chinese.toml` to `german.toml`, `french.toml`, etc. and translate it. Anything left
  out shows in English.

## Download

Players can get the ready-made installer from the
[Releases page](https://github.com/instl999/paradox-new-player-advisor/releases/latest): download the zip, unzip it,
and double-click **Install.bat**. Python is not needed.

## License

[MIT](LICENSE). You are free to use, change and share this mod; keep the copyright notice.

## Roadmap

- **Victoria 3:** DLC features (power blocs), trade-route advice, army supply goods.
- More HOI4 rules: naval and air production, the logistics screen (supply/railways), decisions, and focus-specific
  hints for the major nations.
- Translations: copy `rules/locale/<game>/simp_chinese.toml` to another language and translate it.
