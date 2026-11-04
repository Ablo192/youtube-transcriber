@echo off
title Transcripteur YouTube - Mode Local
cd /d "%~dp0"
echo ========================================================
echo   Lancement du Transcripteur YouTube (Mode Ordinateur)
echo ========================================================
echo.
echo Ouverture de votre navigateur...
start http://localhost:8501
python -m streamlit run youtube_transcriber\app.py
pause

