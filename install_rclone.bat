@echo off
setlocal

echo [1/3] Checking for existing rclone...
where rclone >nul 2>nul
if %errorlevel%==0 (
    echo rclone is already installed.
    rclone version
    goto :done
)

echo [2/3] Checking for winget...
where winget >nul 2>nul
if not %errorlevel%==0 (
    echo winget was not found.
    echo Please download rclone from:
    echo https://rclone.org/downloads/
    start "" "https://rclone.org/downloads/"
    goto :failed
)

echo [3/3] Installing rclone with winget...
winget install --id Rclone.Rclone --exact --source winget
if not %errorlevel%==0 (
    echo winget failed to install rclone.
    echo Please download rclone from:
    echo https://rclone.org/downloads/
    start "" "https://rclone.org/downloads/"
    goto :failed
)

echo Verifying rclone...
where rclone >nul 2>nul
if not %errorlevel%==0 (
    echo rclone was installed, but it is not available in PATH yet.
    echo Close and reopen Command Prompt or PowerShell, then run:
    echo rclone version
    goto :done
)

rclone version

:done
echo.
echo Done. You can now run start_gui.bat.
pause
exit /b 0

:failed
echo.
echo Installation was not completed.
pause
exit /b 1
