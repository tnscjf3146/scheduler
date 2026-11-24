# Builds the frontend, the exe and the installer into .\dist
#   .\build.ps1
# Not 'Stop': pnpm and PyInstaller log to stderr, which Windows PowerShell would turn into errors.
# Each step is checked by its exit code instead.
Push-Location $PSScriptRoot
try {
    function Invoke-Step($name, [scriptblock]$cmd) {
        Write-Host "== $name"
        & $cmd
        if ($LASTEXITCODE) { throw "$name failed (exit $LASTEXITCODE)" }
    }
    Invoke-Step 'frontend' { pnpm --dir frontend build }
    Invoke-Step 'exe' { & backend\.venv\Scripts\pyinstaller backend\scheduler.spec --noconfirm --distpath dist --workpath build }
    Invoke-Step 'installer' { & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /Q installer\scheduler.iss }
    Remove-Item build -Recurse -Force  # PyInstaller's scratch folder
    Get-ChildItem dist -File | Format-Table Name, @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }
}
finally {
    Pop-Location
}
