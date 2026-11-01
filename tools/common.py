"""Helpers shared by the game backends: rule validation and script text formatting."""
import re

RULE_KEYS = ("id", "category", "target", "priority", "title", "advice", "why", "steps", "trigger")
TEXT_FIELDS = ("title", "advice", "why", "steps")


class RulesError(Exception):
    pass


def check_identifier(where, value):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise RulesError(f"{where} '{value}' must be lowercase letters, digits and underscores")


def check_text(where, text):
    if '"' in text:
        raise RulesError(f"{where} may not contain double quotes")


def check_braces(where, text):
    depth = 0
    for line in text.splitlines():
        for ch in line.split("#", 1)[0]:
            depth += (ch == "{") - (ch == "}")
            if depth < 0:
                raise RulesError(f"{where}: unexpected '}}'")
    if depth:
        raise RulesError(f"{where}: {depth} unclosed '{{'")


def validate_rules(rules, targets, categories, dlcs, max_steps, max_per_category):
    """Checks the parts of the rules file that every game shares."""
    seen = set()
    for rule in rules:
        rid = rule.get("id", "?")
        for key in RULE_KEYS:
            if key not in rule:
                raise RulesError(f"rule '{rid}' is missing '{key}'")
        check_identifier("rule id", rid)
        if rid in seen:
            raise RulesError(f"duplicate rule id '{rid}'")
        seen.add(rid)
        if rule["target"] != "none" and rule["target"] not in targets:
            raise RulesError(f"rule '{rid}' targets unknown button '{rule['target']}'")
        if rule["category"] not in categories:
            raise RulesError(f"rule '{rid}' has unknown category '{rule['category']}'")
        if "dlc" in rule and rule["dlc"] not in dlcs:
            raise RulesError(f"rule '{rid}' names unknown dlc '{rule['dlc']}' (add it to [dlc])")
        if not 1 <= len(rule["steps"]) <= max_steps:
            raise RulesError(f"rule '{rid}' must have 1–{max_steps} steps")
        for key in ("title", "advice", "why"):
            check_text(f"rule '{rid}' {key}", rule[key])
        for step in rule["steps"]:
            check_text(f"rule '{rid}' step", step)
        check_braces(f"rule '{rid}' trigger", rule["trigger"])
    for cat in categories:
        count = sum(r["category"] == cat for r in rules)
        if count > max_per_category:
            raise RulesError(f"category '{cat}' has {count} rules; the panel fits {max_per_category} per tab")


def validate_locales(game, locales, languages, rules, targets, categories, ui_keys):
    """Checks rules/locale/<game>/*.toml against the rules: known keys only, matching step counts."""
    if "english" not in locales:
        raise RulesError(f"rules/locale/{game}/english.toml is missing")
    by_id = {r["id"]: r for r in rules}
    missing = set(ui_keys) - set(locales["english"].get("ui", {}))
    if missing:
        raise RulesError(f"rules/locale/{game}/english.toml is missing ui keys: {', '.join(sorted(missing))}")
    for lang, loc in locales.items():
        if lang not in languages:
            raise RulesError(f"locale '{lang}' is not a {game} language (expected one of {', '.join(languages)})")
        known = {"ui": locales["english"]["ui"], "targets": targets, "categories": categories, "rules": by_id}
        for key, names in known.items():
            for name in loc.get(key, {}):
                if name not in names:
                    raise RulesError(f"locale '{lang}': unknown {key} entry '{name}'")
        for value in [*loc.get("ui", {}).values(), *loc.get("targets", {}).values(),
                      *loc.get("categories", {}).values()]:
            check_text(f"locale '{lang}'", value)
        for rid, text in loc.get("rules", {}).items():
            for field, value in text.items():
                if field not in TEXT_FIELDS:
                    raise RulesError(f"locale '{lang}': rule '{rid}' has unknown field '{field}'")
                for v in value if field == "steps" else [value]:
                    check_text(f"locale '{lang}': rule '{rid}' {field}", v)
            if "steps" in text and len(text["steps"]) != len(by_id[rid]["steps"]):
                raise RulesError(f"locale '{lang}': rule '{rid}' has {len(text['steps'])} steps, "
                                 f"English has {len(by_id[rid]['steps'])}")


def rule_text(rule, loc):
    """The rule's title/advice/why/steps in one language, falling back to English per field."""
    return {**{k: rule[k] for k in TEXT_FIELDS}, **loc.get("rules", {}).get(rule["id"], {})}


def rank_rules(rules):
    """Numbers the rules (rule["index"], 1-based, file order) and ranks them (rule["rank"], 0 = most important).

    Returns (rules by global rank, {target: rules on that button by rank}).
    """
    for i, rule in enumerate(rules, 1):
        rule["index"] = i
    ranked = sorted(rules, key=lambda r: (r["priority"], r["index"]))
    for rank, rule in enumerate(ranked):
        rule["rank"] = rank
    by_target = {}
    for rule in ranked:
        if rule["target"] != "none":
            by_target.setdefault(rule["target"], []).append(rule)
    return ranked, by_target


def indent(text, tabs):
    pad = "\t" * tabs
    return "\n".join(pad + line if line.strip() else "" for line in text.strip().splitlines())


def header_comment(game):
    return f"# Generated from rules/{game}.toml by tools/build.py — edit the rules, not this file.\n\n"
