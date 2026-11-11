@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set LOG=%cd%\start.log
echo [%date% %time%] === launch start.bat === > "%LOG%"

echo ========================================
echo   ShiShi Launcher
echo   %cd%
echo ========================================
echo.

REM ---- 0. Clean old processes ----
echo [0/3] Killing old processes on 8000 / 8080...
echo [0] clean ports >> "%LOG%"
set killed=0
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000" ^| findstr LISTENING') do (
    echo   backend PID=%%p
    taskkill /f /pid %%p >nul 2>&1
    set killed=1
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8080" ^| findstr LISTENING') do (
    echo   frontend PID=%%p
    taskkill /f /pid %%p >nul 2>&1
    set killed=1
)
if "!killed!"=="0" echo   (none)
timeout /t 2 /nobreak >nul

REM ---- 1. Start backend ----
echo [1/3] Starting backend (FastAPI on port 8000)...
echo [1] cd "%~dp0back" >> "%LOG%"
pushd "%~dp0back"
echo [1] python -m uvicorn app.main:app --reload --port 8000 >> "%LOG%"
start "ShiShi-Backend" cmd /k "python -m uvicorn app.main:app --reload --port 8000"
set be_err=%ERRORLEVEL%
popd
echo [1] start backend exitcode=!be_err! >> "%LOG%"

REM poll port up to 25s
set ready=0
for /L %%i in (1,1,25) do (
    timeout /t 1 /nobreak >nul
    netstat -ano 2>nul | findstr ":8000" | findstr LISTENING >nul && (
        set ready=1
        echo   [OK] backend up after %%i seconds
        echo [1] backend ready at t=%%i >> "%LOG%"
        goto :backend_ready
    )
)
echo   [WARN] backend not ready yet after 25s
echo [1] backend NOT ready after 25s >> "%LOG%"
:backend_ready

REM ---- 2. Start frontend ----
echo.
echo [2/3] Starting frontend (Flutter Web -d edge on port 8080)...
echo   First compile needs ~40-60s. Edge opens automatically when done.
pushd "%~dp0front\mealmind"
echo [2] flutter run -d edge --web-port 8080 >> "%LOG%"
start "ShiShi-Frontend" cmd /k "flutter run -d edge --web-port 8080"
set fe_err=%ERRORLEVEL%
popd
echo [2] start frontend exitcode=!fe_err! >> "%LOG%"

echo.
echo ========================================
echo [3/3] Done! (see start.log if something failed)
echo   Backend docs : http://localhost:8000/docs
echo   Frontend     : Edge auto-opens
echo ========================================
echo.
echo [%date% %time%] === start.bat finished === >> "%LOG%"
echo Log saved to: %LOG%
echo.
pause
endlocal
