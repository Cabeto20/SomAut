@echo off
rem Abre a interface de testes. Na primeira vez (ou se a pasta foi copiada de outro lugar),
rem prepara o ambiente Python do projeto (.venv) e instala as bibliotecas.
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" goto preparar
"%PY%" -c "import numpy, scipy, sounddevice, websocket, yaml" >nul 2>nul || goto preparar
goto rodar

:preparar
echo Preparando o ambiente do projeto (so na primeira vez; pode levar alguns minutos)...
where python >nul 2>nul || (
  echo.
  echo Python nao encontrado. Instale o Python 3.11 ou mais novo em https://www.python.org
  echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
  pause
  exit /b 1
)
python -m venv --clear .venv || (pause & exit /b 1)
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
echo Ambiente pronto.
if "%~1"=="--so-preparar" exit /b 0

:rodar
if "%~1"=="--so-preparar" exit /b 0
"%PY%" interface.py
pause
