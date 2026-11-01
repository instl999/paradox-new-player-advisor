"""Bundles a built mod with a double-click Windows installer into dist/<name>.zip."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BAT = """@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0files\\install.ps1" {args}
echo.
pause
"""


def package(game, backend, build_root, mod, dlc_names=()):
    """backend: the game's backend module, which supplies GAME_FOLDER and PACKAGE_README."""
    folder = mod["folder"]
    with open(os.path.join(ROOT, "installer", "install.ps1"), encoding="utf-8") as f:
        script = (f.read().replace("__MOD_FOLDER__", folder).replace("__MOD_NAME__", mod["name"])
                  .replace("__GAME_FOLDER__", backend.GAME_FOLDER)
                  .replace("__DLC_NAMES__", ", ".join("'" + n.replace("'", "''") + "'" for n in dlc_names)))

    top = f"{folder}-{game}-{mod['version']}"
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    zip_path = os.path.join(ROOT, "dist", top + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # Windows batch and PowerShell 5.1 files want CRLF line endings.
        z.writestr(f"{top}/Install.bat", BAT.format(args="").replace("\n", "\r\n"))
        z.writestr(f"{top}/Uninstall.bat", BAT.format(args="-Uninstall").replace("\n", "\r\n"))
        readme = backend.PACKAGE_README.format(name=mod["name"], version=mod["version"], days=mod["snooze_days"])
        z.writestr(f"{top}/README.txt", readme.replace("\n", "\r\n"))
        z.write(os.path.join(ROOT, "LICENSE"), f"{top}/LICENSE.txt")
        z.writestr(f"{top}/files/install.ps1", script.replace("\r\n", "\n").replace("\n", "\r\n"))
        descriptor = os.path.join(build_root, folder + ".mod")
        if os.path.exists(descriptor):
            z.write(descriptor, f"{top}/files/{folder}.mod")
        mod_dir = os.path.join(build_root, folder)
        for dirpath, _, filenames in os.walk(mod_dir):
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, mod_dir).replace(os.sep, "/")
                z.write(full, f"{top}/files/{folder}/{rel}")
    return zip_path
