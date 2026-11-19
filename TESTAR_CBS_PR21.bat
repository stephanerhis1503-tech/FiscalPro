@echo off
setlocal
chcp 65001 >nul
title FiscalPro - TESTE CBS PR21

set "ORIGEM=%LOCALAPPDATA%\FiscalPro"
set "COPIA=%LOCALAPPDATA%\FiscalPro_TESTE_PR21"
set "EXEC=%~dp0FiscalPro_PR21\FiscalPro_PR21.exe"

if not exist "%EXEC%" (
  echo ERRO: FiscalPro_PR21.exe nao foi encontrado nesta pasta.
  echo Extraia o ZIP completo antes de executar este arquivo.
  pause
  exit /b 2
)

tasklist /FI "IMAGENAME eq FiscalPro.exe" | find /I "FiscalPro.exe" >nul
if not errorlevel 1 (
  echo Feche o FiscalPro instalado antes de preparar o teste.
  pause
  exit /b 2
)

if not exist "%COPIA%\fiscalpro.db" (
  if not exist "%ORIGEM%\fiscalpro.db" (
    echo Base original nao localizada em "%ORIGEM%\fiscalpro.db".
    echo Nenhum dado sera alterado. Confira onde esta a sua instalacao.
    pause
    exit /b 2
  )
  echo Copiando os dados para uma pasta ISOLADA de teste...
  robocopy "%ORIGEM%" "%COPIA%" /E /R:1 /W:1 /XD "%ORIGEM%\backups" "%ORIGEM%\logs" >nul
  if errorlevel 8 (
    echo Falha ao copiar os dados. O FiscalPro original nao foi alterado.
    pause
    exit /b 3
  )
)

set "FISCALPRO_DATA_DIR=%COPIA%"
echo.
echo Abrindo FiscalPro PR21 com dados de teste em:
echo %COPIA%
echo.
echo Nao use esta versao para transmitir apuracoes.
"%EXEC%"
if errorlevel 1 (
  echo.
  echo FiscalPro PR21 terminou com erro. Tire um print da mensagem.
  pause
)
endlocal
