@echo off
cd /d "%~dp0"

start "Backend" cmd /k python main.py

timeout /t 5 /nobreak > nul

start "Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 3 /nobreak > nul

start "" "http://localhost:5173/"