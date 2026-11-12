@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.12 "%~dp0setup_windows.py" %*
    goto finished
  )
  py -3.13 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -3.13 "%~dp0setup_windows.py" %*
    goto finished
  )
)
where python >nul 2>&1
if not errorlevel 1 (
  python "%~dp0setup_windows.py" %*
  goto finished
)
echo Python was not found. Install 64-bit Python 3.12 or 3.13 with pip and Tcl/Tk.
echo See README.md for instructions.
pause
exit /b 1
:finished
set "setup_result=%errorlevel%"
if not "%setup_result%"=="0" echo Setup failed. Read the error above and README.md.
pause
exit /b %setup_result%
