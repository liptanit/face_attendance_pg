@echo off
set NSSM=C:\NSSM\nssm.exe

net stop FaceAttendance-Worker
net stop FaceAttendance-Caddy
net stop FaceAttendance-Backend

"%NSSM%" remove FaceAttendance-Worker confirm
"%NSSM%" remove FaceAttendance-Caddy confirm
"%NSSM%" remove FaceAttendance-Backend confirm

echo Uninstalled.
