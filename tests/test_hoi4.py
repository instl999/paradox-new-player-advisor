"""Structural checks on the generated HOI4 mod. No game needed:

    python -m unittest discover tests

They catch the mistakes the game would only report in error.log (or silently ignore): a scripted GUI
naming an element that isn't in its window, a missing localisation key or sprite, an undefined
scripted trigger, a malformed .dds, or a localisation file without its BOM.
"""
import copy
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
import hoi4_backend  # noqa: E402
import lint  # noqa: E402
import pdx  # noqa: E402

GUI_EFFECT_SUFFIXES = ("_right_click", "_shift_click", "_control_click", "_alt_click", "_click")
GUI_TRIGGER_SUFFIXES = ("_click_enabled", "_visible")
ELEMENT_TYPES = ("containerWindowType", "buttonType", "iconType", "instantTextBoxType")
LOC_LINE = re.compile(r'^ ([A-Za-z0-9_.]+):0 "(.*)"$')


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


class Hoi4Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = build.load_config("hoi4")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.mod_dir = hoi4_backend.build(copy.deepcopy(cls.config), cls.tmp.name)
        cls.p = cls.config["mod"]["prefix"]
        cls.gui = pdx.parse(read(cls.path(f"interface/{cls.p}_advisor.gui")))
        cls.gfx = pdx.parse(read(cls.path(f"interface/{cls.p}_advisor.gfx")))
        cls.sgui = pdx.parse(read(cls.path(f"common/scripted_guis/{cls.p}_advisor_scripted_guis.txt")))
        cls.triggers = pdx.parse(read(cls.path(f"common/scripted_triggers/{cls.p}_advisor_triggers.txt")))
        cls.loc = {lang: cls.load_loc(lang) for lang in hoi4_backend.LANGUAGES}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def path(cls, rel):
        return os.path.join(cls.mod_dir, rel)

    @classmethod
    def load_loc(cls, lang):
        path = cls.path(f"localisation/{lang}/{cls.p}_advisor_l_{lang}.yml")
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

    def windows(self):
        """{window name: set of element names inside it, at any depth}."""
        out = {}
        for kind, block in ((e.key, e.value) for e in pdx.first(self.gui, "guiTypes")):
            self.assertIn(kind, ELEMENT_TYPES)
            names = {pdx.first(e.value, "name") for e in pdx.walk(block) if e.key in ELEMENT_TYPES}
            out[pdx.first(block, "name")] = names
        return out

    def test_scripted_gui_elements_exist_in_their_window(self):
        windows = self.windows()
        for name, body in ((e.key, e.value) for e in pdx.first(self.sgui, "scripted_gui")):
            window = pdx.first(body, "window_name")
            self.assertIn(window, windows, f"scripted gui {name}: window {window} not in .gui")
            for section, suffixes in (("effects", GUI_EFFECT_SUFFIXES), ("triggers", GUI_TRIGGER_SUFFIXES)):
                for key in (e.key for e in pdx.first(body, section, [])):
                    suffix = next((s for s in suffixes if key.endswith(s)), None)
                    self.assertIsNotNone(suffix, f"{name}: {key} has no known {section} suffix")
                    element = key[:-len(suffix)]
                    self.assertIn(element, windows[window], f"{name}: {key} names no element in {window}")

    def test_scripted_triggers_are_defined(self):
        defined = {e.key for e in self.triggers}
        used = set()
        for tree in (self.sgui, self.triggers):
            used |= {e.key for e in pdx.walk(tree) if isinstance(e.key, str) and e.key.startswith(self.p + "_")
                     and e.value in ("yes", "no")}
        self.assertFalse(used - defined, f"undefined scripted triggers: {sorted(used - defined)}")

    def test_every_rule_has_a_trigger_and_card(self):
        defined = {e.key for e in self.triggers}
        windows = self.windows()
        for rule in self.config["rule"]:
            self.assertIn(f"{self.p}_rule_{rule['id']}", defined)
            self.assertIn(f"{self.p}_card_{rule['id']}", windows[f"{self.p}_panel_window"])
            self.assertIn(f"{self.p}_guide_{rule['id']}", windows[f"{self.p}_guide_window"])
            if rule["target"] != "none":
                self.assertIn(f"{self.p}_badge_{rule['id']}", windows[f"{self.p}_target_{rule['target']}_window"])

    def test_gui_text_keys_exist_in_every_language(self):
        keys = {e.value for e in pdx.walk(self.gui) if e.key in ("text", "pdx_tooltip", "buttonText")}
        for lang, entries in self.loc.items():
            missing = sorted(keys - set(entries))
            self.assertFalse(missing, f"{lang}: {len(missing)} missing, e.g. {missing[:5]}")
        english = set(self.loc["english"])
        for lang, entries in self.loc.items():
            self.assertEqual(set(entries), english, f"{lang} keys differ from english")

    def test_sprites_exist_and_textures_are_valid(self):
        sprites = {}
        for e in pdx.first(self.gfx, "spriteTypes"):
            sprites[pdx.first(e.value, "name")] = pdx.first(e.value, "texturefile")
        used = {e.value for e in pdx.walk(self.gui) if e.key == "spriteType"}
        self.assertFalse(used - set(sprites), f"undefined sprites: {sorted(used - set(sprites))}")
        for name, texture in sprites.items():
            with open(self.path(texture), "rb") as f:
                data = f.read()
            self.assertEqual(data[:4], b"DDS ", texture)
            height, width = struct.unpack("<2I", data[12:20])
            self.assertEqual(len(data), 128 + width * height * 4, texture)

    def test_dlc_dependent_badges_have_both_placements(self):
        windows = self.windows()
        for name, t in self.config["targets"].items():
            if "without_dlc" not in t or not any(r["target"] == name for r in self.config["rule"]):
                continue
            self.assertIn(f"{self.p}_target_{name}_window", windows)
            self.assertIn(f"{self.p}_target_{name}_nodlc_window", windows)

    def test_translations_are_used(self):
        zh = self.loc["simp_chinese"]
        rule = self.config["rule"][0]
        self.assertNotEqual(zh[f"{self.p}_{rule['id']}_title"], self.loc["english"][f"{self.p}_{rule['id']}_title"])


class RulesValidation(unittest.TestCase):
    def build_with(self, mutate):
        config = build.load_config("hoi4")
        mutate(config)
        with tempfile.TemporaryDirectory() as tmp:
            hoi4_backend.build(config, tmp)

    def assertRejected(self, mutate, message):
        with self.assertRaisesRegex(common.RulesError, message):
            self.build_with(mutate)

    def test_duplicate_id(self):
        self.assertRejected(lambda c: c["rule"].append(dict(c["rule"][0])), "duplicate rule id")

    def test_unknown_target(self):
        self.assertRejected(lambda c: c["rule"][0].update(target="nowhere"), "unknown button")

    def test_unbalanced_trigger(self):
        self.assertRejected(lambda c: c["rule"][0].update(trigger="OR = { has_war = yes"), "unclosed")

    def test_quote_in_text(self):
        self.assertRejected(lambda c: c["rule"][0].update(title='Say "hi"'), "double quotes")

    def test_unknown_trigger(self):
        self.assertRejected(lambda c: c["rule"][0].update(trigger="has_warr = yes"), "unknown trigger 'has_warr'")

    def test_translation_step_count(self):
        def mutate(c):
            rid = c["rule"][0]["id"]
            c["locale"]["simp_chinese"]["rules"][rid]["steps"] = ["one"]
        self.assertRejected(mutate, "steps, English has")


class TriggerLint(unittest.TestCase):
    known = lint.load_known("hoi4")

    def unknown(self, text):
        return lint.unknown_triggers(text, self.known)

    def test_logic_and_scopes_are_walked(self):
        text = """
        OR = { has_war = yes NOT = { bogus_a = yes } }
        any_enemy_country = { bogus_b = yes is_major = yes }
        GER = { bogus_c = yes }
        64 = { bogus_d = yes }
        """
        self.assertEqual(self.unknown(text), ["bogus_a", "bogus_b", "bogus_c", "bogus_d"])

    def test_trigger_arguments_are_not_checked(self):
        self.assertEqual(self.unknown("stockpile_ratio = { archetype = infantry_equipment ratio < 0.2 }"), [])

    def test_every_rule_passes(self):
        for rule in build.load_config("hoi4")["rule"]:
            self.assertEqual(self.unknown(rule["trigger"]), [], rule["id"])


if __name__ == "__main__":
    unittest.main()
