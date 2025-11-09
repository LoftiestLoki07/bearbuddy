@echo off
REM git-snapshot.bat - add, commit, push current repo

REM 1) figure out current branch
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set CURBRANCH=%%b

REM 2) show current status
echo --- git status (before) ---
git status --short
echo.

REM 3) stage everything (tracked + new)
git add -A

REM 4) check if there is anything to commit
set CHANGED=
for /f "delims=" %%i in ('git status --porcelain') do set CHANGED=1

if not defined CHANGED (
    echo Nothing to commit.
    goto push
)

REM 5) use user message or default
set MSG=%*
if "%MSG%"=="" set MSG=auto snapshot

echo Committing with message: "%MSG%"
git commit -m "%MSG%"

:push
REM 6) push to origin on current branch
echo Pushing to origin/%CURBRANCH% ...
git push origin %CURBRANCH%

echo.
echo Git snapshot done in %cd%.
