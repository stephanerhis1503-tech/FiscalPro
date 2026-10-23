@echo off
setlocal
cd /d "%~dp0"
echo FiscalPro - Classificador de e-mails
echo.
echo Esta janela verifica o Gmail e aplica somente marcadores de empresa.
echo Ela nao baixa anexos, nao arquiva e nao exclui mensagens.
echo Feche esta janela para parar.
echo.
python -m src.robo_email.executor_marcadores --intervalo 60
if errorlevel 1 (
  echo.
  echo O classificador terminou com erro.
  pause
)
endlocal
