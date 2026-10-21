# Installs (or removes, with -Uninstall) the mod into the Hearts of Iron IV user mod folder.
# __MOD_FOLDER__ and __MOD_NAME__ are filled in by tools/package.py.
param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$ModFolder = '__MOD_FOLDER__'
$ModName = '__MOD_NAME__'
$GameFolder = 'Hearts of Iron IV'
$DlcNames = @(__DLC_NAMES__)
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Finds the game's install folder through Steam's library list (returns $null if not found).
function Find-GameInstall {
    $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
    if (-not $steam) { return $null }
    $libraries = @($steam)
    $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
    if (Test-Path $vdf) {
        foreach ($m in [regex]::Matches((Get-Content -Raw $vdf), '"path"\s+"([^"]+)"')) {
            $libraries += $m.Groups[1].Value -replace '\\\\', '\'
        }
    }
    foreach ($lib in $libraries) {
        $p = Join-Path $lib "steamapps\common\$GameFolder"
        if (Test-Path $p) { return $p }
    }
    return $null
}

# Compares the DLC names the mod checks with the DLC actually installed, and saves a report.
function Write-DlcReport($reportPath) {
    $game = Find-GameInstall
    $lines = @("DLC check for $ModName", "")
    if (-not $game) {
        $lines += "Game install folder not found through Steam; DLC check skipped."
    } else {
        $installed = @()
        foreach ($f in Get-ChildItem (Join-Path $game 'dlc') -Recurse -Filter '*.dlc' -ErrorAction SilentlyContinue) {
            $m = Select-String -Path $f.FullName -Pattern '^\s*name\s*=\s*"([^"]+)"' | Select-Object -First 1
            if ($m) { $installed += $m.Matches[0].Groups[1].Value }
        }
        $lines += "Game folder: $game"
        $lines += ""
        foreach ($name in $DlcNames) {
            if ($installed -contains $name) { $lines += "  [found]     $name" }
            else { $lines += "  [not found] $name  (its advice stays hidden: DLC not owned, or the name is different)" }
        }
        $lines += ""
        $lines += "All DLC names installed:"
        $lines += ($installed | Sort-Object | ForEach-Object { "  $_" })
    }
    $lines | Set-Content -Encoding UTF8 $reportPath
    $lines | ForEach-Object { Write-Host $_ }
}

function Find-GameDir {
    $docs = @([Environment]::GetFolderPath('MyDocuments'),
              (Join-Path $env:USERPROFILE 'Documents'),
              (Join-Path $env:USERPROFILE 'OneDrive\Documents')) | Select-Object -Unique
    foreach ($d in $docs) {
        $p = Join-Path $d "Paradox Interactive\$GameFolder"
        if (Test-Path $p) { return $p }
    }
    Write-Host "Could not find the $GameFolder folder in Documents\Paradox Interactive."
    Write-Host "This usually means the game has not been started on this PC yet."
    $answer = Read-Host "Create it and install anyway? (y/n)"
    if ($answer -notmatch '^[yY]') { throw "Cancelled. Start $GameFolder once, then run the installer again." }
    $p = Join-Path $docs[0] "Paradox Interactive\$GameFolder"
    New-Item -ItemType Directory -Force $p | Out-Null
    return $p
}

$modRoot = Join-Path (Find-GameDir) 'mod'
$dest = Join-Path $modRoot $ModFolder
$descriptor = Join-Path $modRoot "$ModFolder.mod"

if ($Uninstall) {
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    if (Test-Path $descriptor) { Remove-Item -Force $descriptor }
    Write-Host "$ModName has been removed from $modRoot"
    return
}

New-Item -ItemType Directory -Force $modRoot | Out-Null
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }   # replace an older version cleanly
Copy-Item -Recurse (Join-Path $Here $ModFolder) $dest
Copy-Item -Force (Join-Path $Here "$ModFolder.mod") $descriptor

Write-Host ""
try { Write-DlcReport (Join-Path $dest 'dlc_check.txt') } catch { Write-Host "DLC check skipped: $_" }

Write-Host ""
Write-Host "$ModName installed to:"
Write-Host "  $dest"
Write-Host ""
Write-Host "Next: open the Paradox launcher, go to Playsets, add '$ModName' to a playset, and play."
