"""Bundles a built mod with a double-click Windows installer into dist/<name>.zip."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BAT = """@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0files\\install.ps1" {args}
echo.
pause
"""

README = """{name} {version} - Hearts of Iron IV

INSTALL
  1. Unzip this folder anywhere (do not run it from inside the zip).
  2. Double-click Install.bat.
  3. In the Paradox launcher, add "{name}" to a playset and start the game.

UNINSTALL
  Double-click Uninstall.bat.

USING IT
  A gold "!" badge on a topbar button means the advisor has a recommendation there.
  Hover over it to read why. Left-click opens a step-by-step guide. Right-click snoozes it for {days} days.
  The lightbulb button opens the panel with all advice, sorted into tabs (Economy, Military,
  Politics & Diplomacy, DLC Features). Click any card in it for its guide.

  The installer saves a DLC report to mod\\new_player_advisor\\dlc_check.txt. Advice for DLC you
  don't own stays hidden.

  If the badges don't line up with the buttons, open the Advisor and click "Show all icons" to see every
  badge at once. Then report the offsets (a screenshot helps).

NOTE
  Like any mod, this turns off Ironman achievements while it is enabled.
  If something doesn't work, send:  Documents\\Paradox Interactive\\Hearts of Iron IV\\logs\\error.log
"""


def package(game, build_root, mod, dlc_names=()):
    folder = mod["folder"]
    with open(os.path.join(ROOT, "installer", "install.ps1"), encoding="utf-8") as f:
        script = (f.read().replace("__MOD_FOLDER__", folder).replace("__MOD_NAME__", mod["name"])
                  .replace("__DLC_NAMES__", ", ".join("'" + n.replace("'", "''") + "'" for n in dlc_names)))

    top = f"{folder}-{game}-{mod['version']}"
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    zip_path = os.path.join(ROOT, "dist", top + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # Windows batch and PowerShell 5.1 files want CRLF line endings.
        z.writestr(f"{top}/Install.bat", BAT.format(args="").replace("\n", "\r\n"))
        z.writestr(f"{top}/Uninstall.bat", BAT.format(args="-Uninstall").replace("\n", "\r\n"))
        z.writestr(f"{top}/README.txt", README.format(name=mod["name"], version=mod["version"],
                                                      days=mod["snooze_days"]).replace("\n", "\r\n"))
        z.write(os.path.join(ROOT, "LICENSE"), f"{top}/LICENSE.txt")
        z.writestr(f"{top}/files/install.ps1", script.replace("\r\n", "\n").replace("\n", "\r\n"))
        z.write(os.path.join(build_root, folder + ".mod"), f"{top}/files/{folder}.mod")
        mod_dir = os.path.join(build_root, folder)
        for dirpath, _, filenames in os.walk(mod_dir):
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, mod_dir).replace(os.sep, "/")
                z.write(full, f"{top}/files/{folder}/{rel}")
    return zip_path
