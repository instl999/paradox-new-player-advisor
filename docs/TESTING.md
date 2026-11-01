# In-game test checklist

The automated tests (`python -m unittest discover tests`) check that the generated files are consistent. They can't
check that the game accepts them, that the badges line up, or that the triggers fire at the right moment. Run this
checklist in the game before every release. It takes about 30 minutes per game.

Start the game with the `-debug` launch option (Paradox launcher → Game settings → Launch options). Then error.log is
written as you play, and `.gui` files reload while the game runs.

Log file locations:

- HOI4: `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log`
- Victoria 3: `Documents/Paradox Interactive/Victoria 3/logs/error.log`

## Hearts of Iron IV

### A. Loading

- [ ] A1. The launcher lists **New Player Advisor** and it can be added to a playset.
- [ ] A2. Start a new game as Germany (1936). Search error.log for `npa`. **Expected: no lines.** Copy any lines
      into the bug report.
- [ ] A3. The lightbulb button appears in the topbar (below the political power / stability row).

### B. Badges and calibration

- [ ] B1. Open the Advisor (lightbulb) → **Show all icons**. A gold badge appears near the top-right corner of every
      topbar button: Political, Intelligence (with La Résistance), Research, Diplomacy, Trade, Construction,
      Production, Recruit & Deploy, Logistics, Officer Corps (with No Step Back).
- [ ] B2. Each badge sits on its button and covers no other button. If not, note the button and how far off it is
      (a screenshot is best). Fix it in `rules/hoi4.toml` → `[targets.*]` (see README).
- [ ] B3. With "Show all icons" on, every badge has a pulsing ring. **If you see a wide strip of rings instead of one
      pulsing ring**, set `pulse = false` under `[mod]` and report it.
- [ ] B4. Turn "Show all icons" off. Badges remain only on buttons with active advice.

### C. Next move, panel and guide

- [ ] C1. Germany, 1 Jan 1936, unpaused for a day: the **Do this next** bar beside the lightbulb names one piece of
      advice, and that button's badge pulses.
- [ ] C2. Left-click the bar: the guide opens at step 1, the bar hides, and the target button pulses.
- [ ] C3. Next / Back move through the steps; Back is hidden on step 1; Done replaces Next on the last step.
- [ ] C4. All advice: the guide closes and the panel opens. The banner at the top shows the same "Do this next".
- [ ] C5. Tabs switch the cards. Every card has a gold, green or grey icon.
- [ ] C6. Right-click a gold card icon: it turns grey (snoozed). Left-click the grey icon: it wakes up.
- [ ] C7. Right-click the next bar: that advice is snoozed and the bar moves on to the next one.
- [ ] C8. Footer **Next-move bar** hides the bar; clicking it again shows it.
- [ ] C9. Hover tooltips show the title, advice, why text and the click hints, in the game's language.

### D. Advice fires and clears

Play Germany at speed 5 and check these change at the expected moments:

- [ ] D1. "Choose a National Focus" and "Plan Your Research" are active in January 1936 and clear by March 1936.
      (HOI4 has no trigger for an empty research slot or an unchosen focus, so these are timed orientation advice.)
- [ ] D2. Construction badge is active in 1936; it switches to military factories from 1938.
- [ ] D2b. As a small country with tension above 25%: "Train More Divisions" appears. Queue some divisions: it clears
      while they are in training.
- [ ] D2c. Play without La Résistance (disable it in the launcher's DLC list). With "Show all icons", the Research to
      Officer Corps badges still sit on their buttons (they use the `x_without_dlc` positions).
- [ ] D3. Once at war: battle plans, supply and war economy advice appear.
- [ ] D4. Play a small country (e.g. Luxembourg) to 1938: "Look for Allies" appears when world tension passes 50%.
- [ ] D5. Remove all DLC from the playset (or play without it): no DLC-tab advice is active.

### E. Language

- [ ] E1. Switch the game to Simplified Chinese. All advisor text is Chinese and nothing shows a raw key such as
      `npa_toggle_tt`.
- [ ] E2. Switch to German: the advisor text is English (no raw keys).

### F. Removal

- [ ] F1. Save, remove the mod from the playset, load the save. The game loads normally.

## Victoria 3

Before starting the game, run `python tools/preview.py vic3` and open `build/vic3/preview/index.html`: it shows what
the interface should look like.

### G. Loading

- [ ] G1. The launcher lists **New Player Advisor** (Victoria 3, version 0.1.0) and it can be added to a playset.
- [ ] G2. Start a new game as Prussia (or any country). Search error.log for `npa`. **Expected: no lines.** Copy any
      lines into the bug report. Pay special attention to lines about `scripted_widgets`, `GetScriptedGui`,
      `alert_types` or unknown triggers.
- [ ] G3. The lightbulb advisor button appears at the top left, just above the left sidebar.

### H. Badges and calibration

- [ ] H1. Open the Advisor → **Show all icons**. A gold badge appears at the top-right corner of the Politics, Budget,
      Buildings, Market, Military, Diplomacy and Technology sidebar buttons, and each of those buttons has a pulsing
      gold frame around it.
- [ ] H2. Each badge and frame sits on its button. If not, note how far off they are (a screenshot is best) and fix
      `x / y / w / h` in `rules/vic3.toml` → `[targets.*]`.
- [ ] H3. The vanilla sidebar buttons still open their screens when you click them (the frames must be click-through).
- [ ] H4. Repeat H1 at UI scale 125% (Settings → Graphics → UI scale). Badges still line up.

### I. Next move, panel and guide

- [ ] I1. Unpause for a week. The **Do this next** bar beside the advisor button names one piece of advice (on a
      fresh game usually "Pick a Technology to Research" or "Your Construction Is Idle"), and that sidebar button
      pulses.
- [ ] I2. The same advice appears in the game's **Important Actions** list (top of the screen) as "Advisor: …".
      Clicking it opens the right screen.
- [ ] I3. Click the bar: the guide opens at step 1 on the right, the bar hides, the target button keeps pulsing.
- [ ] I4. Next / Back move through the steps; Done on the last step closes the guide. **Open screen** opens the
      right vanilla screen (Budget, Buildings / construction, Market, Technology, Politics → Laws tab for "Pass a New
      Law", Companies for "Establish a Company"). Press it again while that screen is open: the screen stays open.
- [ ] I5. All advice: the guide closes and the panel opens, with the same advice in the banner.
- [ ] I6. Tabs switch the cards; every card shows a gold, green or grey icon. Clicking a card opens its guide.
- [ ] I7. Right-click the gold icon on a card: it turns grey (snoozed) and the bar moves on. Left-click the grey icon:
      it wakes up. Save and load: the snooze is kept.
- [ ] I8. Footer **Next-move bar** hides the bar; click again to show it.
- [ ] I9. Clicking the advisor panel or guide does not click through to the map behind it.

### J. Advice fires and clears

- [ ] J1. Empty the research queue: "Pick a Technology to Research" appears; pick one: it clears within a day.
- [ ] J2. Let the construction queue run empty: "Your Construction Is Idle" appears; queue buildings: it clears.
- [ ] J3. Raise wages until the weekly balance is negative: "You Are Losing Money" appears and becomes "Do this next"
      (unless something more urgent is active).
- [ ] J4. Start enacting a law: "Pass a New Law" clears.
- [ ] J5. Build Government Administration until bureaucracy is positive: "You Lack Bureaucracy" clears.

### K. Language and removal

- [ ] K1. Switch the game to Simplified Chinese: all advisor text is Chinese, no raw keys like `npa_toggle_tt`.
- [ ] K2. Switch to German: advisor text is English, no raw keys.
- [ ] K3. Save, remove the mod, load the save: the game loads normally.
