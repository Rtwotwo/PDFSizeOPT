$ErrorActionPreference='Stop'
$source=Join-Path $PSScriptRoot 'launcher.cs'
$target=Join-Path $PSScriptRoot 'PdfSizeOPT.exe'
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$icon=Join-Path $PSScriptRoot 'assets\app.ico'
& $compiler /nologo /target:winexe /platform:anycpu /r:System.Windows.Forms.dll "/win32icon:$icon" "/out:$target" $source
if ($LASTEXITCODE -ne 0) {throw 'Launcher compilation failed.'}
