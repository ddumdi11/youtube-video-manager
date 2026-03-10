@echo off
title YouTube Video Manager
cd /d "%~dp0"

echo Aktiviere virtuelle Umgebung...
call venv\Scripts\activate.bat

echo Starte YouTube Video Manager...
python yt_app.py

echo App beendet. Deaktiviere Umgebung...
call venv\Scripts\deactivate.bat 2>nul

echo Fertig. Fenster schliesst in 3 Sekunden...
timeout /t 3 /nobreak >nul
exit
