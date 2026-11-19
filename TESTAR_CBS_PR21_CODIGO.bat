@echo off
setlocal
chcp 65001 >nul
title FiscalPro - PR21 (codigo-fonte, dados isolados)
cd /d "%~dp0"
set "ORIGEM=%LOCALAPPDATA%\FiscalPro"
set "COPIA=%LOCALAPPDATA%\FiscalPro_TESTE_PR21"

if not exist "main.py" (
  echo ERRO: main.py nao encontrado. Abra este arquivo na pasta raiz da PR21.
  pause
  exit /b 2
)
tasklist /FI "IMAGENAME eq FiscalPro.exe" | find /I "FiscalPro.exe" >nul
if not errorlevel 1 (
  echo Feche o FiscalPro instalado antes de copiar os dados.
  pause
  exit /b 2
)
if not exist "%COPIA%\fiscalpro.db" (
  if not exist "%ORIGEM%\fiscalpro.db" (
    echo ERRO: base instalada nao encontrada em %ORIGEM%\fiscalpro.db
    echo Nao foi criada nenhuma base de teste.
    pause
    exit /b 2
  )
  echo Criando copia isolada dos dados locais para o teste...
  robocopy "%ORIGEM%" "%COPIA%" /E /R:1 /W:1 /XD "%ORIGEM%\backups" "%ORIGEM%\logs" >nul
  if errorlevel 8 (
    echo ERRO na copia dos dados. Nao abriremos o aplicativo.
    pause
    exit /b 3
  )
)
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado no PATH.
  pause
  exit /b 4
)
set "FISCALPRO_DATA_DIR=%COPIA%"
echo Abrindo FiscalPro da PR21 com dados em %COPIA%
echo Nao transmitir apuracoes nem efetuar baixas nesta versao de teste.
python main.py
if errorlevel 1 (
  echo.
  echo Erro ao abrir. Verifique as bibliotecas instaladas e envie o print.
  pause
)
endlocal
