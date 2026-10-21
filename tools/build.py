"""Build the advisor mod for a game from its rules file.

    python tools/build.py hoi4             # build into build/hoi4/
    python tools/build.py hoi4 --install   # build, then copy into the game's mod folder
    python tools/build.py hoi4 --package   # build, then make dist/<mod>.zip with a double-click installer
"""
import argparse
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hoi4_backend  # noqa: E402
import install  # noqa: E402
import package  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKENDS = {"hoi4": hoi4_backend}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game", choices=sorted(BACKENDS))
    parser.add_argument("--install", action="store_true", help="copy the built mod into the game's mod folder")
    parser.add_argument("--package", action="store_true", help="make an installer zip in dist/")
    parser.add_argument("--game-dir", help="game user folder, if not in the default Documents location")
    args = parser.parse_args()

    with open(os.path.join(ROOT, "rules", f"{args.game}.toml"), "rb") as f:
        config = tomllib.load(f)
    locale_dir = os.path.join(ROOT, "rules", "locale", args.game)
    config["locale"] = {}
    for name in sorted(os.listdir(locale_dir)):
        if name.endswith(".toml"):
            with open(os.path.join(locale_dir, name), "rb") as f:
                config["locale"][name[:-5]] = tomllib.load(f)

    out_root = os.path.join(ROOT, "build", args.game)
    try:
        mod_dir = BACKENDS[args.game].build(config, out_root)
    except hoi4_backend.RulesError as e:
        sys.exit(f"rules/{args.game}.toml: {e}")
    print(f"Built {len(config['rule'])} rules -> {os.path.relpath(mod_dir, ROOT)}")

    if args.package:
        zip_path = package.package(args.game, out_root, config["mod"], config.get("dlc", {}).values())
        print(f"Packaged -> {os.path.relpath(zip_path, ROOT)}")

    if args.install:
        dest = install.install(args.game, out_root, config["mod"]["folder"], args.game_dir)
        print(f"Installed -> {dest}")
        print("Enable it in the Paradox launcher under Playsets.")


if __name__ == "__main__":
    main()
