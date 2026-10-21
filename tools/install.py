"""Copies a built mod into the game's user mod folder (Documents/Paradox Interactive/<game>/mod)."""
import os
import shutil

GAME_FOLDERS = {"hoi4": "Hearts of Iron IV", "vic3": "Victoria 3"}


def find_game_dir(game):
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, "Documents"), os.path.join(home, "OneDrive", "Documents")]
    for docs in candidates:
        path = os.path.join(docs, "Paradox Interactive", GAME_FOLDERS[game])
        if os.path.isdir(path):
            return path
    raise FileNotFoundError(
        f"Could not find the {GAME_FOLDERS[game]} user folder in {' or '.join(candidates)}. "
        "Launch the game once, or pass --game-dir."
    )


def install(game, build_root, folder, game_dir=None):
    mod_root = os.path.join(game_dir or find_game_dir(game), "mod")
    os.makedirs(mod_root, exist_ok=True)
    dest = os.path.join(mod_root, folder)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(os.path.join(build_root, folder), dest)
    shutil.copy2(os.path.join(build_root, folder + ".mod"), os.path.join(mod_root, folder + ".mod"))
    return dest
