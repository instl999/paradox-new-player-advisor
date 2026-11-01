"""Structural checks on the generated Victoria 3 mod. No game needed:

    python -m unittest discover tests

They catch what the game would only report in error.log (or ignore silently): a GUI naming a scripted GUI,
localization key or texture that doesn't exist, a malformed data-binding expression, an undefined scripted
trigger, an alert without its localization, or a broken metadata file.
"""
import copy
import json
import os
import re
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build  # noqa: E402
import common  # noqa: E402
import lint  # noqa: E402
import pdx  # noqa: E402
import vic3_backend  # noqa: E402

LOC_LINE = re.compile(r'^ ([A-Za-z0-9_.]+): "(.*)"$')
GUI_FILES = ("npa_advisor_hud.gui", "npa_advisor_windows.gui")


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


class Vic3Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = build.load_config("vic3")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.mod_dir = vic3_backend.build(copy.deepcopy(cls.config), cls.tmp.name)
        cls.p = cls.config["mod"]["prefix"]
        cls.gui_text = {name: read(cls.path(f"gui/{name}")) for name in GUI_FILES}
        cls.gui = {name: pdx.parse(text) for name, text in cls.gui_text.items()}
        cls.sgui = pdx.parse(read(cls.path(f"common/scripted_guis/{cls.p}_advisor_scripted_guis.txt")))
        cls.triggers = pdx.parse(read(cls.path(f"common/scripted_triggers/{cls.p}_advisor_triggers.txt")))
        cls.alerts = pdx.parse(read(cls.path(f"common/alert_types/{cls.p}_advisor_alerts.txt")))
        cls.values = pdx.parse(read(cls.path(f"common/script_values/{cls.p}_advisor_values.txt")))
        cls.loc = {lang: cls.load_loc(lang) for lang in vic3_backend.LANGUAGES}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def path(cls, rel):
        return os.path.join(cls.mod_dir, rel)

    @classmethod
    def load_loc(cls, lang):
        path = cls.path(f"localization/{lang}/{cls.p}_advisor_l_{lang}.yml")
        with open(path, "rb") as f:
            raw = f.read()
        assert raw.startswith(b"\xef\xbb\xbf"), f"{path} has no UTF-8 BOM"
        lines = raw[3:].decode("utf-8").splitlines()
        assert lines[0] == f"l_{lang}:", f"{path} header is {lines[0]!r}"
        entries = {}
        for line in lines[1:]:
            m = LOC_LINE.match(line)
            assert m, f"{path}: malformed line {line!r}"
            assert m.group(1) not in entries, f"{path}: duplicate key {m.group(1)}"
            assert '"' not in m.group(2), f"{path}: stray quote in {m.group(1)}"
            entries[m.group(1)] = m.group(2)
        return entries

    def all_gui_entries(self):
        for tree in self.gui.values():
            yield from pdx.walk(tree)

    def bindings(self):
        """Every [ ... ] data-binding expression in the GUI files."""
        for text in self.gui_text.values():
            yield from re.findall(r'"\[(.*?)\]"', text)

    def test_widget_names_are_unique(self):
        for name, tree in self.gui.items():
            # Animation states (state = { name = ... }) are named per widget, so they may repeat.
            names = [pdx.first(e.value, "name") for e in pdx.walk(tree) if isinstance(e.value, list)
                     and e.key != "state"]
            names = [n for n in names if n]
            dupes = {n for n in names if names.count(n) > 1}
            self.assertFalse(dupes, f"{name}: duplicate widget names {sorted(dupes)[:5]}")

    def test_bindings_are_well_formed(self):
        for expr in self.bindings():
            self.assertEqual(expr.count("("), expr.count(")"), expr)
            self.assertEqual(expr.count("'") % 2, 0, expr)

    def test_referenced_scripted_guis_exist(self):
        defined = {e.key for e in self.sgui}
        used = {m for expr in self.bindings() for m in re.findall(r"GetScriptedGui\('([^']+)'\)", expr)}
        self.assertTrue(used)
        self.assertFalse(used - defined, f"undefined scripted GUIs: {sorted(used - defined)[:5]}")
        for e in self.sgui:
            self.assertEqual(pdx.first(e.value, "scope"), "country", e.key)

    def test_scripted_triggers_are_defined(self):
        defined = {e.key for e in self.triggers}
        used = set()
        for tree in (self.sgui, self.triggers, self.alerts):
            used |= {e.key for e in pdx.walk(tree) if isinstance(e.key, str) and e.key.startswith(self.p + "_")
                     and e.value in ("yes", "no")}
        self.assertFalse(used - defined, f"undefined scripted triggers: {sorted(used - defined)}")

    def test_text_keys_exist_in_every_language(self):
        keys = {e.value for e in self.all_gui_entries() if e.key in ("text", "tooltip")}
        english = set(self.loc["english"])
        for lang, entries in self.loc.items():
            missing = sorted(keys - set(entries))
            self.assertFalse(missing, f"{lang}: {len(missing)} missing, e.g. {missing[:5]}")
            self.assertEqual(set(entries), english, f"{lang} keys differ from english")

    def test_textures_exist_and_are_valid(self):
        used = {e.value for e in self.all_gui_entries() if e.key == "texture"}
        used |= {e.value for e in pdx.walk(self.alerts) if e.key == "texture"}
        for texture in used:
            with open(self.path(texture), "rb") as f:
                data = f.read()
            self.assertEqual(data[:4], b"DDS ", texture)
            height, width = struct.unpack("<2I", data[12:20])
            self.assertEqual(len(data), 128 + width * height * 4, texture)

    def test_alerts_have_localization(self):
        english = self.loc["english"]
        for e in self.alerts:
            for suffix in ("name", "desc", "hint", "action"):
                self.assertIn(f"alert_{e.key}_{suffix}", english)
            self.assertIn(f"{e.key}_setting_name", english)
            self.assertEqual(pdx.first(e.value, "type"), "important_action")

    def test_every_rule_has_badge_guide_and_card(self):
        names = {pdx.first(e.value, "name") for e in self.all_gui_entries() if isinstance(e.value, list)}
        for rule in self.config["rule"]:
            rid = rule["id"]
            for name in (f"{self.p}_card_{rid}", f"{self.p}_next_{rid}",
                         *(f"{self.p}_guide_{rid}_{s}" for s in range(1, len(rule["steps"]) + 1))):
                self.assertTrue(name in names, f"missing widget {name}")
            if rule["target"] != "none":
                self.assertTrue(f"{self.p}_badge_{rid}" in names, f"no badge for {rid}")
                self.assertTrue(f"{self.p}_pulse_{rule['target']}" in names, f"no pulse for {rule['target']}")

    def test_scripted_widgets_point_at_root_widgets(self):
        text = read(self.path("gui/scripted_widgets/npa_advisor_widgets.txt"))
        for line in text.strip().splitlines():
            gui_path, widget = (part.strip() for part in line.split("="))
            self.assertTrue(os.path.exists(self.path(gui_path)), gui_path)
            roots = [pdx.first(e.value, "name") for e in pdx.parse(read(self.path(gui_path)))]
            self.assertEqual(roots, [widget])

    def test_script_value(self):
        self.assertEqual(pdx.first(self.values[0].value, "value"), "infrastructure")

    def test_metadata(self):
        with open(self.path(".metadata/metadata.json"), encoding="utf-8") as f:
            meta = json.load(f)
        for key in ("name", "id", "version", "supported_game_version", "game_id"):
            self.assertIn(key, meta)
        self.assertEqual(meta["game_id"], "victoria3")

    def test_translations_are_used(self):
        rid = self.config["rule"][0]["id"]
        self.assertNotEqual(self.loc["simp_chinese"][f"{self.p}_{rid}_title"],
                            self.loc["english"][f"{self.p}_{rid}_title"])


class RulesValidation(unittest.TestCase):
    def assertRejected(self, mutate, message):
        config = build.load_config("vic3")
        mutate(config)
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(common.RulesError, message):
            vic3_backend.build(config, tmp)

    def test_unknown_trigger(self):
        self.assertRejected(lambda c: c["rule"][0].update(trigger="is_at_warr = yes"), "unknown trigger")

    def test_formatting_characters_in_text(self):
        self.assertRejected(lambda c: c["rule"][0].update(advice="Costs $5"), r"\[ \] \$ or #")

    def test_target_needs_a_panel(self):
        self.assertRejected(lambda c: c["targets"]["budget"].pop("panel"), "needs 'panel'")

    def test_every_rule_passes_lint(self):
        known = lint.load_known("vic3")
        for rule in build.load_config("vic3")["rule"]:
            self.assertEqual(lint.unknown_triggers(rule["trigger"], known, {"npa_infrastructure_balance"}), [],
                             rule["id"])


if __name__ == "__main__":
    unittest.main()
