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

REM ---- 0. Backend environment (auto-repair) ----
REM Always use the project's environment, not an unrelated system Python.
set "PYEXE=%~dp0back\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [0/4] back\.venv is missing ^(it is not tracked by git^).
    echo       Creating it now - one time only, takes about a minute.
    echo [0] venv missing, creating >> "%LOG%"
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python is not on PATH. Install Python 3.10+ and retry.
        echo [0] python not found on PATH >> "%LOG%"
        pause
        exit /b 1
    )
    python -m venv "%~dp0back\.venv"
    if not exist "%PYEXE%" (
        echo [ERROR] Failed to create back\.venv. See the messages above.
        echo [0] venv creation failed >> "%LOG%"
        pause
        exit /b 1
    )
    echo       Installing backend dependencies...
    "%PYEXE%" -m pip install --disable-pip-version-check -r "%~dp0back\requirements.txt" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check the network, then run manually:
        echo   back\.venv\Scripts\python.exe -m pip install -r back\requirements.txt
        echo [0] pip install failed, see log >> "%LOG%"
        pause
        exit /b 1
    )
    echo       [OK] Backend environment ready.
)

"%PYEXE%" -c "import uvicorn, fastapi, sqlmodel, pymysql" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Backend dependencies are missing. See start.log.
    echo Run: back\.venv\Scripts\python.exe -m pip install -r back\requirements.txt
    echo [0] dependency import check failed >> "%LOG%"
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
echo [1/4] Checking existing backend...
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

REM ---- 2. Start backend ----
echo [2/4] Starting backend (FastAPI on port 8000)...
echo [2] cd "%~dp0back" >> "%LOG%"
pushd "%~dp0back"
echo [2] Using project Python: "%PYEXE%" >> "%LOG%"
start "ShiShi-Backend" cmd /k ""%PYEXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
set be_err=%ERRORLEVEL%
popd
echo [2] start backend exitcode=!be_err! >> "%LOG%"

REM Require a real backend health response before opening the frontend.
set ready=0
for /L %%i in (1,1,25) do (
    timeout /t 1 /nobreak >nul
    powershell -NoProfile -Command "try { $r = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1 && (
        set ready=1
        echo   [OK] backend health check passed on attempt %%i
        echo [2] backend ready at t=%%i >> "%LOG%"
        goto :backend_ready
    )
)
echo   [ERROR] Backend did not become healthy. Check the ShiShi-Backend window.
echo [2] backend health check failed >> "%LOG%"
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

REM ---- 3. Start frontend ----
echo.
echo [3/4] Starting frontend (Flutter Web -d edge on port 8080)...
echo   First compile needs ~40-60s. Edge opens automatically when done.
pushd "%~dp0front\mealmind"
echo [3] flutter run -d edge --web-port 8080 --dart-define=API_BASE=http://127.0.0.1:8000 >> "%LOG%"
start "ShiShi-Frontend" cmd /k "flutter run -d edge --web-port 8080 --dart-define=API_BASE=http://127.0.0.1:8000"
set fe_err=%ERRORLEVEL%
popd
echo [3] start frontend exitcode=!fe_err! >> "%LOG%"

REM Watch the port so a silent compile failure is visible here, not guessed later.
echo   [4/4] Waiting for the page on http://127.0.0.1:8080 ...
set web_up=0
for /L %%i in (1,1,90) do (
    timeout /t 1 /nobreak >nul
    netstat -ano 2>nul | findstr /R /C:":8080 .*LISTENING" >nul && (
        set web_up=1
        echo   [OK] Frontend is serving after ~%%i s.
        echo [3] frontend listening at t=%%i >> "%LOG%"
        goto :launch_done
    )
)
echo   [!] Port 8080 did not come up in 90s.
echo       If Edge did not open, check the ShiShi-Frontend window for a compile error.
echo [3] frontend port 8080 not listening within 90s >> "%LOG%"

:launch_done
echo.
echo ========================================
echo [4/4] Done! (see start.log if something failed)
echo   Backend docs : http://localhost:8000/docs
echo   Frontend     : http://localhost:8080  (Edge auto-opens)
echo ========================================
echo.
echo [%date% %time%] === start.bat finished === >> "%LOG%"
echo Log saved to: %LOG%
echo.
pause
endlocal
