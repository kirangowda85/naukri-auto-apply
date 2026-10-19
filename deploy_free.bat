@echo off
title Naukri Auto-Apply Studio - Free Remote Deployment
echo ======================================================================
echo   Naukri Auto-Apply ^& Profile Booster Studio - Free Deployment
echo ======================================================================
echo.
echo [1/2] Starting Streamlit Studio on port 8501...
start /b python -m streamlit run app.py --server.port 8501
timeout /t 3 /nobreak >nul

echo [2/2] Generating Free Public HTTPS Link (Accessible from anywhere)...
echo.
echo Local Dashboard:  http://localhost:8501
echo Tunnel endpoint password (if prompted): run "curl ifconfig.me" or check your public IP.
echo.
npx -y localtunnel --port 8501
pause
