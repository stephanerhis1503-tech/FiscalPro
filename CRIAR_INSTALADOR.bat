@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0build\windows\build_installer.ps1" (
    echo.
    echo A rotina de build do instalador nao veio no projeto recebido.
    echo A base 17.8.73 esta validada para execucao por INICIAR_FISCALPRO.bat.
    echo Nao sera criado um instalador incompleto.
    echo.
    pause
    exit /b 2
)
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build\windows\build_installer.ps1"
if errorlevel 1 (
    echo.
    echo Nao foi possivel concluir a criacao do instalador.
    echo Leia a mensagem de erro exibida acima.
    echo.
    pause
    exit /b 1
)
echo.
echo O instalador do FiscalPro foi criado com sucesso.
echo.
pause
