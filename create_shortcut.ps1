[CmdletBinding()]
param([switch]$Desktop)

$ErrorActionPreference='Stop'
$root=[System.IO.Path]::GetFullPath($PSScriptRoot)
$python=Join-Path $root 'runtime\pythonw.exe'
if (!(Test-Path -LiteralPath $python)) { $python=Join-Path $root '.venv\Scripts\pythonw.exe' }
$entry=Join-Path $root 'app.py'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $entry)) {
    throw 'Python environment or app.py is missing. Run setup.cmd first.'
}
$shell=New-Object -ComObject WScript.Shell
$destinations=@((Join-Path $root 'PdfSizeOPT.lnk'))
if ($Desktop) {
    $desktopFolder=[Environment]::GetFolderPath('Desktop')
    if (!$desktopFolder) {throw 'Windows did not return a Desktop folder.'}
    $destinations+=Join-Path $desktopFolder 'PdfSizeOPT.lnk'
}
foreach ($destination in $destinations) {
    $shortcut=$shell.CreateShortcut($destination)
    $shortcut.TargetPath=$python
    $shortcut.Arguments='-s "'+$entry+'"'
    $shortcut.WorkingDirectory=$root
    $shortcut.IconLocation=(Join-Path $root 'assets\app.ico')+',0'
    $shortcut.Description='PDFSizeOPT - local high-fidelity PDF compression'
    $shortcut.WindowStyle=1
    $shortcut.Save()
    Write-Output $destination
}
