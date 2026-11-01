# New Player Advisor: Development Specification

| | |
|---|---|
| Document version | 1.0 (2026-10-31) |
| Mod version | HOI4 0.3.0, Victoria 3 0.1.0 |
| Status | HOI4 0.3.0 and Victoria 3 0.1.0 implemented and passing all automated checks; in-game verification pending (§8.4) |
| Source of truth | `rules/<game>.toml` (advice), `tools/` (generators), this document (design) |

## 1. Purpose

Paradox grand strategy games punish inexperience late and silently. A new Hearts of Iron IV player leaves research
slots empty and builds no factories in 1936, then finds out in 1939. A new Victoria 3 player lets the construction
queue run dry and the budget go into deficit, then watches the country default. The game's information is all on
screen, but a beginner can't tell which of it matters right now.

The New Player Advisor answers one question at any moment: **"What should I do next?"** It does this inside the game,
in the style of Civilization VI's advisor:

1. It names **one best next move**, always visible beside the advisor button.
2. It **highlights the screen** where each recommendation is carried out (a gold badge on that button; the best move
   pulses).
3. It **walks the player through it**: a guide window with numbered steps and a short explanation of why.
4. It **stops nagging** when the situation is fixed, and the player can snooze any advice.

Learning happens because each guide explains *why* the move is right. A player who has followed "Build civilian
factories" three times no longer needs the badge.

### 1.1 Non-goals

- **Playing for the player.** The mod never takes an action. Every recommendation is carried out by the player.
  Automating moves would remove the learning, and would also mean writing to game state from UI scripts, which is
  fragile and blocks multiplayer use.
- **Optimal play for experts.** The advice targets "solid and safe", not min-maxing. Exploits and meta builds are
  left out.
- **Replacing the vanilla tutorial.** The advisor covers the open game after the tutorial, for any country.
- **Country-specific focus-tree guides.** These may come later, but the core rules must work for every country.

## 2. Users and design principles

**Primary user:** someone in their first 1–20 hours of the game, playing a major or mid-sized country, who knows
the basic controls but not the economy. **Secondary user:** a returning player who has forgotten the systems since
the last big patch.

| # | Principle | Consequence for design |
|---|---|---|
| P1 | Quiet by default | No pop-ups, no pausing. Badges and a one-line strip; the panel opens only on request. |
| P2 | One clear "next" | Exactly one rule is "Do this next" at a time, chosen by a global priority order. |
| P3 | Show where, not just what | Every rule names the screen (target) where it is carried out, and that button is marked. |
| P4 | Explain why | Every rule has a `why` text. The tooltip and the guide both show it. |
| P5 | React to the real state | Triggers test the actual situation (empty queues, deficits, shortages) wherever the game exposes it. Dates are only a fallback. |
| P6 | Go away when done | A rule's trigger turns false once the problem is fixed. Snooze is available for advice the player chooses to ignore. |
| P7 | Never break the game | Only new files, no overwritten vanilla files where avoidable, no gameplay changes. Removing the mod mid-campaign is safe. |
| P8 | Data, not code | All advice lives in one rules file per game. Adding a rule needs no programming. |

## 3. Requirements

### 3.1 Functional

| ID | Requirement | HOI4 | Vic3 |
|---|---|---|---|
| F1 | Evaluate every rule's trigger continuously for the player's country. | ✓ scripted GUI triggers | ✓ scripted GUI `is_shown` |
| F2 | Show a badge on the target button of each active rule; only the highest-priority rule per button. | ✓ topbar | ✓ left sidebar |
| F3 | Show the single top-priority active rule as "Do this next". | ✓ bar + panel banner | ✓ bar + panel banner + native Important Action |
| F4 | Pulse the target of the next move, and the target of the guide that is open. | ✓ animated ring | ✓ animated glow frame |
| F5 | Advisor panel: tabs per category, a card per rule with state (active / fine / snoozed). | ✓ | ✓ |
| F6 | Step-by-step guide: one step at a time, Back / Next / Done, plus the why text. | ✓ | ✓ plus "Open screen" |
| F7 | Snooze a rule for N days (right-click); wake it again from the panel. | ✓ timed flag | ✓ timed variable |
| F8 | Hide DLC-only advice from players without that DLC. | ✓ `has_dlc` | ✓ `has_dlc_feature` (no DLC rules yet) |
| F9 | Every text in English and Simplified Chinese; other game languages show English. | ✓ 10 languages | ✓ 11 languages |
| F10 | Calibration mode that shows all badges at once. | ✓ "Show all icons" | ✓ "Show all icons" |

### 3.2 Non-functional

| ID | Requirement | How it is met |
|---|---|---|
| N1 | No measurable slowdown. | Triggers are cheap (country-scope comparisons). Per-button and "next" triggers short-circuit on the first inactive rule. |
| N2 | Compatible with other mods. | Only new, prefixed files (`npa_`). In Vic3, any overridden vanilla GUI file is kept to the minimum and listed in §6. |
| N3 | Survives patches. | Triggers are linted against a verified list (§8.2); error.log is the in-game check (§9). |
| N4 | Installable without Python. | Release zip with a double-click installer (`Install.bat`). |
| N5 | Buildable on any OS with only Python 3.11+. | Generators use the standard library only; textures are drawn in code and written as uncompressed DDS. |
| N6 | Save-game safe. | State is country flags/variables with the `npa_` prefix. Removing the mod leaves inert flags behind. |

## 4. Architecture

```
rules/<game>.toml ──┐
rules/locale/<game>/*.toml ──┤      tools/build.py
rules/known/<game>_triggers.txt ┘          │
                                 ┌─────────┴──────────┐
                           common.py             lint.py
                    (shared validation)   (trigger names vs. known list)
                                 │
                 ┌───────────────┴───────────────┐
           hoi4_backend.py                  vic3_backend.py
   scripted_triggers, scripted_guis,   scripted triggers, scripted GUIs,
   .gui/.gfx, .dds, localisation       .gui, .dds, localization, metadata
                 │                               │
          build/hoi4/<mod>                 build/vic3/<mod>
                 └──────── install.py / package.py (+ installer/install.ps1)
```

- **One rules file per game.** Each `[[rule]]` holds an id, category (panel tab), target (screen/button), priority,
  optional DLC key, the English title/advice/why/steps, and a trigger in that game's own script language. The
  trigger is copied verbatim into a scripted trigger. The generator never interprets it beyond linting.
- **Backends** know the game's file formats and UI system. They share validation (`common.py`), the script parser
  (`pdx.py`), the icon painter (`art.py`), and the DDS writer (`dds.py`).
- **Generated output is never edited by hand.** Every file starts with a "generated from" header.

### 4.1 Rule data model

| Field | Type | Meaning |
|---|---|---|
| `id` | identifier | Unique; used in every generated name (`npa_rule_<id>`, `npa_<id>_title`, …). |
| `category` | key of `[categories]` | Panel tab. At most 10 rules per tab (panel space). |
| `target` | key of `[targets]` or `"none"` | Screen where the action happens. `none` = panel and next strip only (e.g. map actions). |
| `priority` | integer | **Global** order. Lower = more important. Decides "Do this next", and which badge shows when several rules share a button. |
| `dlc` | key of `[dlc]` (optional) | Rule is hidden when the DLC is missing. |
| `title`, `advice`, `why` | text | Headline (≤ 40 chars), one-sentence action, 2–3 sentence reason. No double quotes. |
| `steps` | 1–6 texts | One instruction per step, starting from the topbar. |
| `trigger` | game script | True when the advice applies, in the player's country scope. |

### 4.2 Priority bands

A single global order makes "Do this next" well defined. Priorities follow these bands, in both games:

| Band | Range | Meaning | Examples |
|---|---|---|---|
| Emergency | 1–19 | Losing the game right now | front collapsing, bankruptcy, out of rifles |
| Idle capacity | 20–39 | Something that should be working is idle | empty research slot, no focus, empty construction queue |
| Core economy | 40–59 | The main growth loop | civilian factories, construction sector, mobilisation law |
| Strengthening | 60–79 | Good but not urgent | laws, advisors, templates, conscription |
| Refinement | 80–99 | Optional systems, mostly DLC | intelligence, MIOs, designers |

Within a band, the more frequent and cheaper-to-fix problem comes first.

### 4.3 Advice-writing standard

- **Title:** imperative or a state ("Build Civilian Factories", "Fuel Is Low"). Title Case in English.
- **Advice:** one sentence, starts with a verb, names the concrete thing to click or pick.
- **Why:** the mechanism in plain words; no numbers that change between patches unless essential.
- **Steps:** step 1 always says which topbar button to click ("the one with the gold badge"). Each step is one
  action. The last step tells the player how to check that it worked.
- **Trigger:** must turn false when the advice has been followed, or the advice will nag forever. Date-only triggers
  are allowed only for one-off orientation advice in the first months.

## 5. Hearts of Iron IV backend

### 5.1 Generated files

| File | Content |
|---|---|
| `common/scripted_triggers/npa_advisor_triggers.txt` | `npa_dlc_<key>`, `npa_rule_<id>` (snooze + DLC + trigger), `npa_show_<id>` (badge: active and no higher-priority rule on the same button), `npa_next_<id>` (active and no higher-priority rule anywhere), `npa_any_active`. |
| `common/scripted_guis/npa_advisor_scripted_guis.txt` | Five scripted GUIs: toggle, next strip, one per target button, panel, guide. All `context_type = player_context`. |
| `interface/npa_advisor.gui` / `.gfx` | Windows and sprites (§5.3). |
| `gfx/interface/npa/*.dds` | Textures painted by `art.py`. |
| `localisation/<lang>/npa_advisor_l_<lang>.yml` | All nine HOI4 languages, UTF-8 with BOM. |
| `descriptor.mod` + `../new_player_advisor.mod` | Launcher descriptors. |

### 5.2 Runtime state (player country)

| Name | Kind | Meaning |
|---|---|---|
| `npa_panel_open` | flag | Panel is open. |
| `npa_debug_show_all` | flag | Calibration mode: every badge and pulse visible. |
| `npa_hide_next` | flag | Player turned the "Do this next" strip off. |
| `npa_snooze_<id>` | timed flag | Rule is snoozed (`days = snooze_days`). |
| `npa_tab` | variable | Selected panel tab. |
| `npa_guide` | variable | 1-based index of the rule whose guide is open; 0 = closed. |
| `npa_step` | variable | Current guide step. |

Flags and variables live on the country, so in multiplayer each player has their own advisor state.

### 5.3 Interface

- **Advisor button** (lightbulb) in `top_bar`, with a small gold "!" when any rule is active. Click toggles the panel.
- **Next strip** beside the button: "Do this next: <title>". Left-click opens the guide; right-click snoozes. Hidden
  while the panel or a guide is open, or when the player turns it off in the panel footer.
- **Badges:** one 20×20 window per target button, attached to `top_bar`, containing one badge per rule (only the
  `npa_show_<id>` one is visible) and a click-through animated ring (`frameAnimatedSpriteType`, 8 frames, 10 fps)
  that is visible while that button holds the next move or the open guide's rule.
- **Panel** (centred, movable): header, "Do this next" banner (or "Nothing urgent" when nothing is active), category
  tabs, up to 10 cards per tab, footer buttons ("Show all icons", "Next-move bar").
- **Guide** (top right, movable): title, current step, why box, Back / All advice / Next / Done.

Badge positions are in `[targets.*]`, measured from a 1920×1080 screenshot at 100% UI scale. See README → Calibrating
badge positions. Vanilla `topbar.gui` groups the Research → Officer Corps buttons so they move 55 px left when the
La Résistance Intelligence button is absent. Those targets set `without_dlc = "lar"` and `x_without_dlc`, and the
generator emits a second badge window for them, shown only without the DLC.

## 6. Victoria 3 backend

### 6.1 Research findings that shaped the design

Target patch: **1.15** (October 2026). All script and GUI names below were checked against the game's own script
documentation for 1.15 (`triggers.log`, `effects.log`, `event_targets.log`, `data_types_*.txt`, published by the
Victoria 3 Modding Co-op) and against vanilla 1.14 game files.

| Question | Finding | Consequence |
|---|---|---|
| Can a mod add UI without overriding vanilla `.gui` files? | Yes: `gui/scripted_widgets/<file>.txt` lines `gui/<file>.gui = <root widget>` register new top-level widgets (used by the Community Mod Framework). | Two new windows, zero vanilla GUI overrides (P7, N2). |
| How does the GUI read script state? | `GetScriptedGui('x').IsShown(GuiScope.SetRoot(GetPlayer.MakeScope).End)` evaluates a scripted GUI's `is_shown` trigger for the player. | One scripted GUI per rule state (rule / show / next / snoozed). |
| Where can UI-only state live? | `GetVariableSystem.Set/Clear/Toggle/Exists/HasValue`: per-client, not saved, not synced. | Panel, tab, guide and step need no game-state writes and no multiplayer commands. |
| How to open a vanilla screen? | `InformationPanelBar.OpenPanelTabDontToggle('<panel>', '<tab>')` (plain `OpenPanelTab` closes a panel that is already open); markets need `OpenMarketPanelTab(AccessPlayer.AccessFirstMarket, 'default')`. Panel names are the sidebar's own (`production_methods` / `construction_queues` for construction). | The guide has an **Open screen** button for the rule's target. |
| Native advice channels? | `common/alert_types` with `type = important_action` and `open_panel` show in the vanilla Important Actions list. Tutorial lessons can highlight vanilla widgets but `start_tutorial_lesson` "does nothing if the tutorial is not running". | Each rule gets an alert that is valid only while it is "Do this next". Tutorial lessons are not used. |
| Journal entries? | Format changed in 1.15 (`outcome = {}` replaced complete/fail); they clutter the journal and can't point at a screen. | Not used. |
| Where are the sidebar buttons? | `gui/information_panel_bar.gui`: bar at y = 200, buttons at offsets 0/50/100/150/200 (politics … military, `sidebar_button_size` 48×50) and 270/310/… (`sidebar_button_size_small` 42×40). | Badge and highlight boxes in `[targets.*]`, still to be confirmed in game. |
| Which layer? | `gui/layers.gui`: `layer_ingame_menu` (−223) is *below* `layer_ingame_hud` (−221, which holds the outliner and the pause menu); popups are −185. | HUD part on `layer_ingame_hud`; panel and guide on `layer_lens_toolbar` (−201), above the HUD and below event popups. Both hide with the pause menu and game-over screen (vanilla's `hud_visibility` condition) and when there is no played country. |
| What triggers exist for real state? | `has_wasted_construction`, `net_total_income`, `gold_reserves_limit`, `scaled_debt`, `market = { market_has_goods_shortage }`, `bureaucracy/authority/influence`, `government_legitimacy`, `enacting_any_law`, `country_turmoil`, `literacy_rate`, `is_diplomatic_play_target`, … | Every Vic3 rule reacts to actual state; none is date-only. The verified list is `rules/known/vic3_triggers.txt`. |

### 6.2 Generated files

| File | Content |
|---|---|
| `.metadata/metadata.json` | Launcher metadata (`game_id = victoria3`, `supported_game_version = 1.15.*`). |
| `common/scripted_triggers/npa_advisor_triggers.txt` | `npa_rule_<id>`, `npa_show_<id>`, `npa_next_<id>`, `npa_any_active`, as in HOI4; snooze is a timed variable. |
| `common/scripted_guis/npa_advisor_scripted_guis.txt` | `npa_{rule,show,next,snoozed}_<id>` and `npa_target_next_<button>` (read state), `npa_snooze_<id>` / `npa_wake_<id>` (the only writes). |
| `common/script_values/npa_advisor_values.txt` | `npa_infrastructure_balance` (state: infrastructure − usage). |
| `common/alert_types/npa_advisor_alerts.txt` | One `important_action` alert per rule, valid while it is the next move. |
| `gui/scripted_widgets/npa_advisor_widgets.txt` | Registers the two windows. |
| `gui/npa_advisor_hud.gui` | `layer_ingame_hud`: advisor button, "Do this next" bar (hidden while a vanilla side panel is open), per sidebar button a pulsing glow frame, per rule a badge. |
| `gui/npa_advisor_windows.gui` | `layer_lens_toolbar`: panel (banner, tabs, cards, footer) and guide (one page per rule × step), placed left of the outliner. |
| `gfx/interface/npa/*.dds` | Same painted textures as HOI4, plus the glow frame and alert icon. |
| `localization/<lang>/npa_advisor_l_<lang>.yml` | All 11 Vic3 languages (note `localization` with a z), UTF-8 with BOM. |

### 6.3 Runtime state

| Name | Where | Meaning |
|---|---|---|
| `npa_panel` | GUI variable | Panel open. |
| `npa_tab` | GUI variable | Selected category; unset = first tab. |
| `npa_guide` / `npa_step` | GUI variables | Open guide's rule id and step. Each step is its own page, so Back/Next simply set the step number. |
| `npa_show_all` | GUI variable | Calibration mode. |
| `npa_hide_next` | GUI variable | "Do this next" bar turned off. |
| `npa_snooze_<id>` | Country variable, `days = snooze_days` | Rule snoozed. Set and cleared through scripted GUI effects, so it is synchronised in multiplayer. |

GUI variables are not saved: after loading a game the panel is closed and the bar is visible, which is the desired
default.

### 6.4 Pulse highlight

There is one glow frame per sidebar button. It is an `icon` inside a widget with three animation states (`_show` → fade → glow → fade …, 0.5 s / 0.7 s),
the same technique as vanilla's `highlight_tutorial_ui`. It is click-through (`alwaystransparent`), so the vanilla
button underneath still works. It is visible when one of the button's rules is the next move (`npa_target_next_<button>`), or when one of their
guides is open.

### 6.5 Preview

`python tools/preview.py vic3 [--lang simp_chinese]` renders the generated GUI as HTML
(`build/vic3/preview/index.html`): it evaluates every `visible` binding for a sample situation and draws the HUD,
the panel and a guide with the real textures and text. It is the main way to check layout and wording without the
game.

## 7. Content plan

### 7.1 Hearts of Iron IV (31 rules)

| Band | Rules |
|---|---|
| Emergency | front collapsing (5), infantry equipment shortage (10), low fuel (15), convoys under attack (18) |
| Idle capacity | choose focus (20), plan research (22), train divisions (25), expand conscription in war (28), war economy (30), check decisions (36) |
| Core economy | civilian factories (40), partial mobilisation (42), military factories (45), look for allies (48), import resources (50) |
| Strengthening | air superiority (60), conscription (61), spend political power (62), stability (64), war support (66), division template (68), battle plans (70), supply (72), autonomy (78) |
| Refinement (DLC) | intelligence agency (80, 84), officer corps (82), MIOs (85), tank designer (86), aircraft designer (88), special projects (90) |

HOI4 has no trigger for an empty research slot, an unchosen focus, idle factories or an empty construction queue
(confirmed against the trigger documentation for 1.16). "Choose a focus", "Plan research" and "Check decisions" are
therefore orientation advice for the first months of 1936. "Train divisions" clears once divisions are in training
(`amount_manpower_in_deployment_queue`).

### 7.2 Victoria 3 (20 rules)

| Band | Rules |
|---|---|
| Emergency | in default (5), threatened by a diplomatic play (8), losing money (10), debt above half the limit (15) |
| Idle capacity | no research (20), idle construction (22), bureaucracy < 0 (25), authority < 0 (28), influence < 0 (30), war (35), treasury full (38) |
| Core economy | more construction sectors (40), low legitimacy (45), infrastructure shortfall (48), three or more goods shortages (52), unemployment (58) |
| Strengthening | turmoil (60), literacy (66), establish a company (70), pass a law (74, an always-on reminder) |

The order follows the vanilla tutorial objective's own sub-goals (fix the budget deficit, expand construction,
research) and the community beginner's guide (never let construction idle; keep the construction goods cheap; keep
bureaucracy positive; pass one law at a time).

### 7.3 Planned next

- HOI4: naval production, air base and port construction, focus-specific hints for the seven majors.
- Vic3: DLC features (power blocs, companies' prosperity), trade route advice once the 1.15 trade system settles,
  education via the institution level, army supply goods.
- Both: more translations (only the interface strings need a translator to start; untranslated rules show English).

## 8. Build, verification and release

### 8.1 Commands

```bash
python tools/build.py hoi4            # build/hoi4/
python tools/build.py vic3            # build/vic3/
python tools/build.py hoi4 --install  # copy into Documents/Paradox Interactive/<game>/mod
python tools/build.py hoi4 --package  # dist/<mod>-hoi4-<version>.zip with Install.bat
python tools/preview.py vic3          # build/vic3/preview/index.html: the Vic3 UI without the game
python -m unittest discover tests     # structural tests, no game needed
```

### 8.2 Automated checks (every build)

| Check | Catches |
|---|---|
| Rule validation (`common.validate_rules`) | Missing fields, duplicate ids, unknown targets/categories/DLC, step count, quotes, unbalanced braces. |
| Locale validation (`common.validate_locales`) | Unknown keys, missing UI keys, step counts that differ from English. |
| Trigger lint (`lint.py`) | Trigger names not in `rules/known/<game>_triggers.txt`, a list built from the game documentation and the wiki, with sources. |
| Brace check on every generated script | Generator bugs. |

### 8.3 Structural tests (`tests/`)

The tests build each game into a temporary folder, parse the output with `pdx.py`, and check things the game would
only report in error.log or ignore silently:

- every scripted-GUI effect/trigger names an element that exists in its window;
- every scripted trigger used is defined;
- every text key referenced by the GUI exists in every language file, and all language files have the same keys;
- every sprite exists, and every texture is a well-formed DDS of the right size;
- localisation files have a BOM and the right header;
- invalid rules files are rejected with a clear message.

### 8.4 In-game verification

No game is available in the development environment, so the following must be checked in the game before each
release. The checklist lives in `docs/TESTING.md`.

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A trigger was renamed in a patch, so the rule never fires | Medium | One rule silent | Trigger lint; error.log check in the release checklist. |
| Badge coordinates drift with UI scale or patch | High (HOI4) | Badges misplaced | Calibration mode; coordinates in the rules file; parent window token so they move with the topbar. |
| Scripted GUI triggers evaluated too often (performance) | Low | Frame time | Short-circuiting triggers; measure with the game's `-debug` FPS counter. |
| Vanilla GUI file overridden by the Vic3 mod conflicts with other UI mods | Medium | Load order issues | Override as little as possible; document the file; prefer standalone windows. |
| Advice goes stale after balance patches | Medium | Bad advice | Advice avoids patch-specific numbers; `supported_version` per release. |
| HOI4 frame-animated pulse sprite drawn as a strip instead of animating | Low | Cosmetic | `pulse = false` in `[mod]` turns it off; checklist item B3. |
| HOI4 scripted GUIs are re-evaluated every tick (the wiki says `dirty` only limits property updates) | Low | Frame time | Hidden windows (panel, guide) skip their element triggers; the always-visible part is about 40 cheap triggers. |
| Vic3 sidebar boxes (from the vanilla templates) are off, or differ at other UI scales | Low | Badges misplaced | "Show all icons" calibration; positions in `[targets.*]`; the whole widget scales with the UI like vanilla. |
| Vic3 1.15 renames a GUI function or trigger | Low | Advisor hidden or rule silent | Names checked against 1.15 docs; error.log check in the checklist; native alerts still work if the custom GUI fails. |
| Vic3 alerts duplicate vanilla alerts (e.g. no research) | Medium | Noise | Only the single "Do this next" alert is ever valid; it can be switched off in the game's alert settings. |

## 10. Milestones

| Milestone | Content | State |
|---|---|---|
| M1 | HOI4 advisor: badges, panel, guides, snooze, 2 languages, installer | Done (0.2.0) |
| M2 | Shared toolchain: common validation, script parser, trigger lint, structural tests | Done |
| M3 | HOI4 "Do this next" strip, banner and pulse; state-reactive triggers; global priorities | Done (0.3.0) |
| M4 | Victoria 3 backend and first rule set, English and Chinese | Done (0.1.0) |
| M5 | In-game verification of both games (checklist in `docs/TESTING.md`) | Needs a Windows PC with the games |
| M6 | Release: GitHub release zips for both games | After M5 |
