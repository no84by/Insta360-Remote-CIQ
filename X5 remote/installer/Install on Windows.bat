@echo off
rem Insta360 X5 Remote - Windows installer. Double-click, then plug in the watch when asked.
rem This file only finds Python 3.8 or newer and starts install.py (without it: py -3 install.py).
rem If Python is missing it can start the official Python installer; you approve it yourself.
setlocal
title Insta360 X5 Remote installer
cd /d "%~dp0"
set "PY_VER=3.13.16"

call :findpy
if not defined PY goto nopython
:run
%PY% "%~dp0install.py" %*
echo.
pause
exit /b

:findpy
set "PY="
set "OK=import sys; sys.exit(sys.version_info < (3, 8))"
py -3 -c "%OK%" >nul 2>&1 && set "PY=py -3" && exit /b
python -c "%OK%" >nul 2>&1 && set "PY=python" && exit /b
rem freshly installed Python is not on this window's PATH yet: look in the usual folders
for %%D in (Python313 Python313-arm64 Python312 Python312-arm64) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\%%D\python.exe""
  if not defined PY if exist "%ProgramFiles%\%%D\python.exe" set "PY="%ProgramFiles%\%%D\python.exe""
)
exit /b

:nopython
echo The installer needs Python 3, which is not installed on this PC.
echo Python is free; the official installer comes from python.org.
echo.
choice /c YN /m "Install Python 3.13 now"
if errorlevel 2 goto manual
where winget >nul 2>&1 && (
  echo Installing with winget. Approve the Windows prompt if one appears...
  winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
) || call :download
call :findpy
if defined PY goto run
echo.
echo Python did not install. Try again, or install it from python.org (link below).

:manual
echo Download Python from https://www.python.org/downloads/windows/
echo During setup, tick "Add python.exe to PATH". Then double-click this file again.
start "" https://www.python.org/downloads/windows/
pause
exit /b

:download
set "ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
set "PYSETUP=%TEMP%\python-%PY_VER%-%ARCH%.exe"
echo Downloading the Python installer from python.org...
curl.exe -fL -o "%PYSETUP%" "https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-%ARCH%.exe" || exit /b
powershell -NoProfile -Command "$s = Get-AuthenticodeSignature '%PYSETUP%'; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Python Software Foundation') { exit 1 }" || (
  echo The download is not validly signed by the Python Software Foundation; not running it.
  exit /b
)
echo Click "Install Now" in the Python window that opens...
start /wait "" "%PYSETUP%" PrependPath=1
exit /b
