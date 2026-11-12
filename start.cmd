@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0runtime\pythonw.exe" (
  start "PdfSizeOPT" "%~dp0runtime\pythonw.exe" -s "%~dp0app.py" %*
  exit /b
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "PdfSizeOPT" "%~dp0.venv\Scripts\pythonw.exe" -s "%~dp0app.py" %*
  exit /b
)
echo Python environment not found. Run setup.cmd first.
pause
exit /b 1
