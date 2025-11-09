@echo off
setlocal

REM === folder to snapshot ===
set REPO_DIR=C:\mini_ERP

cd /d "%REPO_DIR%"

REM init if needed
if not exist ".git" (
    git init
)

REM optional: set username/email once (comment out if you already have global config)
git config user.name  "BearBot"
git config user.email "bear@example.com"

REM stage everything
git add -A

REM make a timestamp
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do (
    set TODAY=%%c%%a%%b
)
for /f "tokens=1-2 delims=: " %%a in ("%time%") do (
    set NOW=%%a%%b
)

REM commit
git commit -m "snapshot %TODAY%_%NOW%" 2>nul

echo.
echo Git snapshot done in %REPO_DIR%.
echo (If it said 'nothing to commit' you didn't change anything.)
echo.

endlocal
