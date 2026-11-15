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

REM Always use the project's environment, not an unrelated system Python.
set "PYEXE=%~dp0back\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [ERROR] Missing back\.venv\Scripts\python.exe. Set up the backend environment first.
    pause
    exit /b 1
)
"%PYEXE%" -c "import uvicorn, fastapi, sqlmodel, pymysql" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Backend dependencies are missing. See start.log.
    echo Run: back\.venv\Scripts\python.exe -m pip install -r back\requirements.txt
    pause
    exit /b 1
)
where flutter >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Flutter is not on PATH.
    pause
    exit /b 1
)

REM Reuse a healthy backend instead of killing/restarting a listening process.
echo [0/3] Checking existing backend...
powershell -NoProfile -Command "try { $r = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Backend already running; reusing it.
    goto :backend_ready
)
netstat -ano 2>nul | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 (
    echo [ERROR] Port 8000 is occupied but the backend health check failed.
    echo Check http://127.0.0.1:8000/api/health and the existing server window.
    pause
    exit /b 1
)

REM ---- 1. Start backend ----
echo [1/3] Starting backend (FastAPI on port 8000)...
echo [1] cd "%~dp0back" >> "%LOG%"
pushd "%~dp0back"
echo [1] Using project Python: "%PYEXE%" >> "%LOG%"
start "ShiShi-Backend" cmd /k ""%PYEXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
set be_err=%ERRORLEVEL%
popd
echo [1] start backend exitcode=!be_err! >> "%LOG%"

REM Require a real backend health response before opening the frontend.
set ready=0
for /L %%i in (1,1,25) do (
    timeout /t 1 /nobreak >nul
    powershell -NoProfile -Command "try { $r = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1 && (
        set ready=1
        echo   [OK] backend health check passed on attempt %%i
        echo [1] backend ready at t=%%i >> "%LOG%"
        goto :backend_ready
    )
)
echo   [ERROR] Backend did not become healthy. Check the ShiShi-Backend window.
echo [1] backend health check failed >> "%LOG%"
echo   Frontend startup cancelled. See start.log and the backend error.
pause
exit /b 1
:backend_ready

REM Repeated launches must not start another Flutter server on the same port.
netstat -ano 2>nul | findstr /R /C:":8080 .*LISTENING" >nul
if not errorlevel 1 (
    echo [OK] Port 8080 is already serving; opening the existing page.
    start "" http://127.0.0.1:8080
    goto :launch_done
)

REM ---- 2. Start frontend ----
echo.
echo [2/3] Starting frontend (Flutter Web -d edge on port 8080)...
echo   First compile needs ~40-60s. Edge opens automatically when done.
pushd "%~dp0front\mealmind"
echo [2] flutter run -d edge --web-port 8080 --dart-define=API_BASE=http://127.0.0.1:8000 >> "%LOG%"
start "ShiShi-Frontend" cmd /k "flutter run -d edge --web-port 8080 --dart-define=API_BASE=http://127.0.0.1:8000"
set fe_err=%ERRORLEVEL%
popd
echo [2] start frontend exitcode=!fe_err! >> "%LOG%"

echo.
echo ========================================
:launch_done
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
