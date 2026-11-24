@echo off
setlocal EnableExtensions
chcp 65001 >nul
title FiscalPro - Ficha Assistida PR27 - TESTE ISOLADO

set "ORIGEM=%LOCALAPPDATA%\FiscalPro"
set "COPIA=%LOCALAPPDATA%\FiscalPro_TESTE_FICHA_PR27"
set "EXEC=%~dp0FiscalPro_Ficha_PR27\FiscalPro_Ficha_PR27.exe"

if not exist "%EXEC%" (
  echo ERRO: Executavel de teste nao encontrado.
  echo Extraia o ZIP inteiro antes de executar este BAT.
  pause
  exit /b 2
)

tasklist /FI "IMAGENAME eq FiscalPro.exe" | find /I "FiscalPro.exe" >nul
if not errorlevel 1 (
  echo Feche o FiscalPro instalado antes do teste.
  pause
  exit /b 2
)

if not exist "%COPIA%\fiscalpro.db" (
  if not exist "%ORIGEM%\fiscalpro.db" (
    echo Banco fiscal original nao encontrado em:
    echo %ORIGEM%\fiscalpro.db
    echo Nenhum arquivo foi alterado. Confira a instalacao.
    pause
    exit /b 3
  )
  echo Criando COPIA dos dados em pasta separada...
  robocopy "%ORIGEM%" "%COPIA%" /E /R:1 /W:1 /XD "%ORIGEM%\backups" "%ORIGEM%\logs" >nul
  if errorlevel 8 (
    echo Falha ao copiar dados. Original preservado.
    pause
    exit /b 4
  )
)

set "FISCALPRO_DATA_DIR=%COPIA%"
echo.
echo ==================================================
echo FISCALPRO PR27 - AMBIENTE SEPARADO DE TESTE
echo Dados usados: %COPIA%
echo ==================================================
echo.
echo NAO use este programa para escrituracao ou envio fiscal.
echo Somente: SPED Inteligente / Auditoria / Ficha Assistida.
echo Clique em Exportar Excel para conferir propostas.
echo Nao aprove ou salve regras reais durante este teste.
echo.
"%EXEC%"
if errorlevel 1 (
  echo O programa de teste terminou com erro.
  echo Tire um print da mensagem exibida.
  pause
)
endlocal
