@echo off
title Instalador - Shimeji AI Companion (Silva)
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
echo.
echo   IMPORTANTE: para a traducao de tela funcionar, instale
echo   o Tesseract-OCR (nao vem pelo pip):
echo   winget install --id UB-Mannheim.TesseractOCR -e
echo ========================================================
pause
