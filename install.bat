@echo off
title Instalador - Shimeji AI Companion (Lumi)
echo ========================================================
echo   Instalando dependencias do Shimeji AI Companion
echo ========================================================

python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ========================================================
echo   Instalacao concluida com sucesso!
echo   Execute run.bat para iniciar o Shimeji AI Companion.
echo ========================================================
pause
