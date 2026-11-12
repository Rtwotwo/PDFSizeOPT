$ErrorActionPreference='Stop'
$root=[System.IO.Path]::GetFullPath($PSScriptRoot)
$python=Join-Path $root 'runtime\pythonw.exe'
if (!(Test-Path -LiteralPath $python)) { $python=Join-Path $root '.venv\Scripts\pythonw.exe' }
$entry=Join-Path $root 'app.py'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $entry)) {
    throw 'Python environment or app.py is missing. Run setup.cmd first.'
}
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut((Join-Path $root 'PdfSizeOPT.lnk'))
$shortcut.TargetPath=$python
$shortcut.Arguments='-s "'+$entry+'"'
$shortcut.WorkingDirectory=$root
$shortcut.IconLocation=(Join-Path $root 'assets\app.ico')+',0'
$shortcut.Description='PdfSizeOPT - local high-fidelity PDF compression'
$shortcut.Save()
Write-Output (Join-Path $root 'PdfSizeOPT.lnk')
