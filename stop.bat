@echo off
setlocal
echo ======= ShiShi Stopper =======
echo.

set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
    echo   Stopping backend PID=%%p
    taskkill /f /pid %%p >nul 2>&1
    set FOUND=1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do (
    echo   Stopping frontend PID=%%p
    taskkill /f /pid %%p >nul 2>&1
    set FOUND=1
)

if "!FOUND!"=="0" (
    echo   No process on 8000/8080.
) else (
    echo   Done.
)
echo.
pause
endlocal
