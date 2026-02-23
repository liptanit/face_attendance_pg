@echo off
setlocal enabledelayedexpansion

REM ===== Project paths =====
set PROJ=D:\face_attendance_pg
set CADDY_DIR=C:\Caddy
set NSSM=C:\NSSM\nssm.exe
set MODELS=D:\face_attendance_models

REM ===== Pre-flight =====
if not exist "%PROJ%\backend" (
  echo ERROR: Project not found at %PROJ%
  exit /b 1
)
if not exist "%NSSM%" (
  echo ERROR: NSSM not found at %NSSM%
  exit /b 1
)
if not exist "%CADDY_DIR%\caddy.exe" (
  echo ERROR: caddy.exe not found at %CADDY_DIR%\caddy.exe
  exit /b 1
)
if not exist "%CADDY_DIR%\Caddyfile" (
  echo ERROR: Caddyfile not found at %CADDY_DIR%\Caddyfile
  echo Copy deploy_windows\Caddyfile -> %CADDY_DIR%\Caddyfile and edit IP if needed.
  exit /b 1
)

if not exist "%MODELS%" mkdir "%MODELS%"

REM ===== Firewall port 8443 =====
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "if (-not (Get-NetFirewallRule -DisplayName 'FaceAttendance HTTPS 8443' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'FaceAttendance HTTPS 8443' -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow | Out-Null }"

REM ===== Install Backend Service =====
"%NSSM%" install FaceAttendance-Backend "C:\Windows\System32\cmd.exe" "/c %PROJ%\deploy_windows\run_backend_service.cmd"
"%NSSM%" set FaceAttendance-Backend AppDirectory "%PROJ%"
"%NSSM%" set FaceAttendance-Backend Start SERVICE_AUTO_START

REM ===== Install Worker Service =====
"%NSSM%" install FaceAttendance-Worker "C:\Windows\System32\cmd.exe" "/c %PROJ%\deploy_windows\run_worker_service.cmd"
"%NSSM%" set FaceAttendance-Worker AppDirectory "%PROJ%"
"%NSSM%" set FaceAttendance-Worker Start SERVICE_AUTO_START

REM ===== Install Caddy Service =====
"%NSSM%" install FaceAttendance-Caddy "%CADDY_DIR%\caddy.exe" "run --config %CADDY_DIR%\Caddyfile"
"%NSSM%" set FaceAttendance-Caddy AppDirectory "%CADDY_DIR%"
"%NSSM%" set FaceAttendance-Caddy Start SERVICE_AUTO_START

REM ===== Start services =====
net start FaceAttendance-Backend
net start FaceAttendance-Caddy
net start FaceAttendance-Worker

echo.
echo DONE.
echo Open: https://172.18.36.46:8443/login
