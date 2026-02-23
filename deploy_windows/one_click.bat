@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =========================================================
REM One-click Admin for Face Attendance (Caddy + NSSM)
REM Paths (ตามที่คุณแจ้ง)
REM =========================================================
set PROJ=D:\face_attendance_pg
set DEPLOY=%PROJ%\deploy_windows
set NSSM=C:\NSSM\nssm.exe
set CADDY_DIR=C:\Caddy
set CADDY_EXE=%CADDY_DIR%\caddy.exe
set CADDYFILE=%CADDY_DIR%\Caddyfile
set URL=https://172.18.36.46:8443/login

set LOGDIR=%PROJ%\logs
set BACKEND_LOG=%LOGDIR%\backend.log
set WORKER_LOG=%LOGDIR%\worker.log
set CADDY_LOG=%LOGDIR%\caddy.log

REM LocalSystem Caddy root CA location
set CADDY_ROOT_CA=C:\Windows\System32\config\systemprofile\AppData\Roaming\Caddy\pki\authorities\local\root.crt

REM =========================================================
REM Helpers
REM =========================================================
:require_admin
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo [ERROR] กรุณารันไฟล์นี้แบบ Run as Administrator
  echo.
  pause
  exit /b 1
)
goto :eof

:check_prereq
if not exist "%PROJ%" (
  echo [ERROR] ไม่พบโปรเจกต์ที่ %PROJ%
  exit /b 1
)
if not exist "%DEPLOY%" (
  echo [ERROR] ไม่พบโฟลเดอร์ %DEPLOY%
  exit /b 1
)
if not exist "%NSSM%" (
  echo [ERROR] ไม่พบ NSSM ที่ %NSSM%
  exit /b 1
)
if not exist "%CADDY_EXE%" (
  echo [ERROR] ไม่พบ Caddy ที่ %CADDY_EXE%
  exit /b 1
)
if not exist "%CADDYFILE%" (
  echo [ERROR] ไม่พบ Caddyfile ที่ %CADDYFILE%
  echo         กรุณาสร้างไฟล์ C:\Caddy\Caddyfile ก่อน
  exit /b 1
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
goto :eof

:svc_exists
REM usage: call :svc_exists ServiceName VarName
set _svc=%~1
sc query "%_svc%" >nul 2>&1
if "%errorlevel%"=="0" (
  set "%~2=1"
) else (
  set "%~2=0"
)
goto :eof

:status_all
echo.
echo =================== SERVICE STATUS ===================
for %%S in (FaceAttendance-Backend FaceAttendance-Caddy FaceAttendance-Worker) do (
  echo.
  echo [%%S]
  sc query "%%S" | findstr /I "STATE START_TYPE WIN32_EXIT_CODE SERVICE_EXIT_CODE"
)
echo ======================================================
echo.
goto :eof

:configure_nssm_logs
echo.
echo [INFO] ตั้งค่า NSSM stdout/stderr logs -> %LOGDIR%
echo [INFO] (ถ้า service ยังไม่ถูก install จะข้าม service นั้น)
echo.

call :svc_exists FaceAttendance-Backend _B
if "!_B!"=="1" (
  "%NSSM%" set FaceAttendance-Backend AppStdout "%BACKEND_LOG%"
  "%NSSM%" set FaceAttendance-Backend AppStderr "%BACKEND_LOG%"
  "%NSSM%" set FaceAttendance-Backend AppStdoutCreationDisposition 4
  "%NSSM%" set FaceAttendance-Backend AppStderrCreationDisposition 4
  "%NSSM%" set FaceAttendance-Backend AppRotateFiles 1
  "%NSSM%" set FaceAttendance-Backend AppRotateOnline 1
  "%NSSM%" set FaceAttendance-Backend AppRotateSeconds 86400
  "%NSSM%" set FaceAttendance-Backend AppRotateBytes 10485760
  echo  - OK: Backend logs
) else (
  echo  - SKIP: Backend service not installed
)

call :svc_exists FaceAttendance-Worker _W
if "!_W!"=="1" (
  "%NSSM%" set FaceAttendance-Worker AppStdout "%WORKER_LOG%"
  "%NSSM%" set FaceAttendance-Worker AppStderr "%WORKER_LOG%"
  "%NSSM%" set FaceAttendance-Worker AppStdoutCreationDisposition 4
  "%NSSM%" set FaceAttendance-Worker AppStderrCreationDisposition 4
  "%NSSM%" set FaceAttendance-Worker AppRotateFiles 1
  "%NSSM%" set FaceAttendance-Worker AppRotateOnline 1
  "%NSSM%" set FaceAttendance-Worker AppRotateSeconds 86400
  "%NSSM%" set FaceAttendance-Worker AppRotateBytes 10485760
  echo  - OK: Worker logs
) else (
  echo  - SKIP: Worker service not installed
)

call :svc_exists FaceAttendance-Caddy _C
if "!_C!"=="1" (
  "%NSSM%" set FaceAttendance-Caddy AppStdout "%CADDY_LOG%"
  "%NSSM%" set FaceAttendance-Caddy AppStderr "%CADDY_LOG%"
  "%NSSM%" set FaceAttendance-Caddy AppStdoutCreationDisposition 4
  "%NSSM%" set FaceAttendance-Caddy AppStderrCreationDisposition 4
  "%NSSM%" set FaceAttendance-Caddy AppRotateFiles 1
  "%NSSM%" set FaceAttendance-Caddy AppRotateOnline 1
  "%NSSM%" set FaceAttendance-Caddy AppRotateSeconds 86400
  "%NSSM%" set FaceAttendance-Caddy AppRotateBytes 10485760
  echo  - OK: Caddy logs
) else (
  echo  - SKIP: Caddy service not installed
)

echo.
echo [INFO] เสร็จแล้ว ถ้าอยากให้ log เริ่มเก็บ ให้ restart service
echo.
goto :eof

:tail_log
REM usage: call :tail_log "path\to\log"
set _f=%~1
if not exist "%_f%" (
  echo [ERROR] ไม่พบไฟล์ log: %_f%
  pause
  goto :eof
)
echo.
echo [INFO] Tailing: %_f%
echo [INFO] กด Ctrl+C เพื่อออก
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%_f%' -Tail 200 -Wait"
goto :eof

:open_url
start "" "%URL%"
goto :eof

:export_caddy_ca
echo.
if not exist "%CADDY_ROOT_CA%" (
  echo [ERROR] ไม่พบ Caddy Root CA:
  echo   %CADDY_ROOT_CA%
  echo.
  echo สาเหตุที่เจอบ่อย:
  echo  - Caddy service ยังไม่เคย start (ยังไม่สร้าง pki)
  echo  - รัน Caddy ไม่ได้อยู่ใต้ LocalSystem
  echo.
  pause
  goto :eof
)
set OUT=%DEPLOY%\caddy_root_ca.crt
copy /Y "%CADDY_ROOT_CA%" "%OUT%" >nul
echo [OK] Export แล้ว: %OUT%
echo.
echo วิธี import บนเครื่อง client (Run as Admin):
echo   certutil -addstore -f "Root" caddy_root_ca.crt
echo.
pause
goto :eof

REM =========================================================
REM MAIN
REM =========================================================
call :require_admin
call :check_prereq || (pause & exit /b 1)

:menu
cls
echo ======================================================
echo   Face Attendance - One Click Admin
echo   Project: %PROJ%
echo   URL    : %URL%
echo ======================================================
echo.
echo  1) Install services (Backend + Caddy + Worker)
echo  2) Start services
echo  3) Stop services
echo  4) Restart services
echo  5) Status (sc query)
echo  6) Configure NSSM logs (stdout/stderr -> %LOGDIR%)
echo  7) Open Web (%URL%)
echo  8) Tail Backend log
echo  9) Tail Worker log
echo 10) Tail Caddy log
echo 11) Export Caddy Root CA (สำหรับเอาไปลง client)
echo 12) Exit
echo.
set /p CH=Select [1-12]: 

if "%CH%"=="1" goto do_install
if "%CH%"=="2" goto do_start
if "%CH%"=="3" goto do_stop
if "%CH%"=="4" goto do_restart
if "%CH%"=="5" goto do_status
if "%CH%"=="6" goto do_logs
if "%CH%"=="7" goto do_open
if "%CH%"=="8" goto do_tail_backend
if "%CH%"=="9" goto do_tail_worker
if "%CH%"=="10" goto do_tail_caddy
if "%CH%"=="11" goto do_export_ca
if "%CH%"=="12" exit /b 0

goto menu

:do_install
echo.
echo [INFO] Running install_services.cmd ...
call "%DEPLOY%\install_services.cmd"
echo.
echo [INFO] ตั้งค่า logs แนะนำให้ทำต่อทันที (เมนู 6) แล้ว restart (เมนู 4)
pause
goto menu

:do_start
echo.
net start FaceAttendance-Backend
net start FaceAttendance-Caddy
net start FaceAttendance-Worker
pause
goto menu

:do_stop
echo.
net stop FaceAttendance-Worker
net stop FaceAttendance-Caddy
net stop FaceAttendance-Backend
pause
goto menu

:do_restart
echo.
net stop FaceAttendance-Worker
net stop FaceAttendance-Caddy
net stop FaceAttendance-Backend
timeout /t 2 >nul
net start FaceAttendance-Backend
net start FaceAttendance-Caddy
net start FaceAttendance-Worker
pause
goto menu

:do_status
call :status_all
pause
goto menu

:do_logs
call :configure_nssm_logs
pause
goto menu

:do_open
call :open_url
goto menu

:do_tail_backend
call :tail_log "%BACKEND_LOG%"
goto menu

:do_tail_worker
call :tail_log "%WORKER_LOG%"
goto menu

:do_tail_caddy
call :tail_log "%CADDY_LOG%"
goto menu

:do_export_ca
call :export_caddy_ca
goto menu
