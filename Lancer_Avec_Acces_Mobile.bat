@echo off
title Transcripteur YouTube - Mode Mobile (Tunnel Cloudflare)
cd /d "%~dp0"
echo ========================================================
echo   Lancement du Transcripteur YouTube (Acces 4G/5G/Mobile)
echo ========================================================
echo.
python youtube_transcriber\run_with_tunnel.py
pause

