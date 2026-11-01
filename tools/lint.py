"""Checks rule triggers against the trigger names known to exist in each game (rules/known/<game>_triggers.txt).

The game only reports a misspelled or removed trigger in error.log, and then treats it as false, so a rule
silently never fires. This catches that at build time. Each line of the known-triggers file is a trigger name,
optionally followed by `# source / notes`. A trailing `*` marks a prefix (e.g. `any_*`). `@scope` after the
name marks a scope change (e.g. `capital_scope @scope`, `any_* @scope`): its block holds more triggers.
Country tags (GER) and state ids (64) are scopes too.
"""
import os
import re

import pdx
from common import RulesError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Blocks whose contents are themselves triggers; anything else is a trigger whose block holds its arguments.
LOGIC = {"AND", "OR", "NOT", "NOR", "NAND", "if", "else_if", "else", "limit", "custom_trigger_tooltip",
         "count_triggers", "hidden_trigger", "trigger_if", "trigger_else_if", "trigger_else"}
# Argument keys inside logic blocks that are not triggers.
LOGIC_ARGS = {"tooltip", "amount", "text", "count", "percent"}


def load_known(game):
    path = os.path.join(ROOT, "rules", "known", f"{game}_triggers.txt")
    names, prefixes, scopes = set(), [], set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            words = line.split("#", 1)[0].split()
            if not words:
                continue
            name = words[0]
            if "@scope" in words[1:]:
                scopes.add(name)
            if name.endswith("*"):
                prefixes.append(name[:-1])
            else:
                names.add(name)
    return names, tuple(prefixes), scopes


def _is_scope(key, scopes):
    if key in scopes or re.fullmatch(r"[A-Z][A-Z0-9]{2}|\d+", key):
        return True
    return any(s.endswith("*") and key.startswith(s[:-1]) for s in scopes)


def unknown_triggers(text, known, scripted=()):
    """Trigger names used in `text` that are neither known game triggers nor in `scripted`."""
    names, prefixes, scopes = known
    out = []

    def visit(entries):
        for e in entries:
            key = e.key
            if key is None:
                continue
            if key in LOGIC:
                if isinstance(e.value, list):
                    visit(e.value)
                continue
            if key in LOGIC_ARGS:
                continue
            if _is_scope(key, scopes):
                if isinstance(e.value, list):
                    visit(e.value)
                continue
            if key not in names and key not in scripted and not key.startswith(prefixes):
                out.append(key)

    visit(pdx.parse(text))
    return out


def check_rules(game, rules, scripted=()):
    known = load_known(game)
    problems = []
    for rule in rules:
        for name in unknown_triggers(rule["trigger"], known, scripted):
            problems.append(f"rule '{rule['id']}': unknown trigger '{name}'")
    if problems:
        raise RulesError("\n  ".join(["triggers not in rules/known/" + game + "_triggers.txt:", *problems]))
