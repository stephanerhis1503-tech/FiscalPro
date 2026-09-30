param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
Set-Location $repoRoot

function Escrever-Etapa([string]$texto) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host $texto -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Localizar-Iscc {
    $candidatos = @()
    $pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $pf64 = [Environment]::GetEnvironmentVariable("ProgramFiles")
    $local = [Environment]::GetEnvironmentVariable("LOCALAPPDATA")

    if ($pf86) {
        $candidatos += (Join-Path $pf86 "Inno Setup 6\ISCC.exe")
    }
    if ($pf64) {
        $candidatos += (Join-Path $pf64 "Inno Setup 6\ISCC.exe")
    }
    if ($local) {
        $candidatos += (Join-Path $local "Programs\Inno Setup 6\ISCC.exe")
    }

    foreach ($candidato in $candidatos) {
        if ($candidato -and (Test-Path $candidato)) {
            return $candidato
        }
    }

    $comando = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($comando) {
        return $comando.Source
    }
    return $null
}

$appInfoPath = Join-Path $repoRoot "src\core\app_info.py"
if (-not (Test-Path $appInfoPath)) {
    throw "Nao encontrei src\core\app_info.py."
}

$appInfo = Get-Content $appInfoPath -Raw -Encoding UTF8
$matchVersao = [regex]::Match($appInfo, 'VERSAO_APP\s*=\s*"([^"]+)"')
$matchArquivo = [regex]::Match($appInfo, 'VERSAO_ARQUIVO_WINDOWS\s*=\s*"([^"]+)"')
if (-not $matchVersao.Success -or -not $matchArquivo.Success) {
    throw "Nao consegui identificar a versao do FiscalPro em app_info.py."
}
$versao = $matchVersao.Groups[1].Value
$versaoArquivo = $matchArquivo.Groups[1].Value

Escrever-Etapa "FiscalPro $versao - preparando ambiente de build"

$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
$usarPy = $true
if (-not $launcher) {
    $launcher = Get-Command python.exe -ErrorAction SilentlyContinue
    $usarPy = $false
}
if (-not $launcher) {
    throw "Python nao encontrado. Instale o Python 3 e marque a opcao de adiciona-lo ao PATH."
}

$venvDir = Join-Path $repoRoot ".venv_instalador"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Criando ambiente isolado do instalador..."
    if ($usarPy) {
        & $launcher.Source -3 -m venv $venvDir
    } else {
        & $launcher.Source -m venv $venvDir
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar o ambiente virtual do instalador."
    }
}

Escrever-Etapa "Instalando/atualizando dependencias"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar o pip." }

$requirements = Join-Path $repoRoot "requirements.txt"
if (-not (Test-Path $requirements)) {
    throw "requirements.txt nao encontrado."
}
& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependencias do FiscalPro." }

& $venvPython -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o PyInstaller." }

Escrever-Etapa "Validando importacao do FiscalPro"
& $venvPython -c "import main; print('Importacao principal OK')"
if ($LASTEXITCODE -ne 0) {
    throw "O codigo nao passou na validacao de importacao. Corrija o erro exibido antes de gerar o instalador."
}

$distDir = Join-Path $repoRoot "dist"
$distApp = Join-Path $distDir "FiscalPro"
$workDir = Join-Path $repoRoot "build\pyinstaller"
if (Test-Path $distApp) {
    Remove-Item $distApp -Recurse -Force
}
if (Test-Path $workDir) {
    Remove-Item $workDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $workDir | Out-Null

Escrever-Etapa "Gerando FiscalPro.exe com PyInstaller"

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "FiscalPro",
    "--icon", (Join-Path $repoRoot "assets\fiscalpro.ico"),
    "--distpath", $distDir,
    "--workpath", (Join-Path $workDir "work"),
    "--specpath", (Join-Path $workDir "spec"),
    "--paths", $repoRoot,
    "--add-data", ((Join-Path $repoRoot "assets") + ";assets"),
    "--add-data", ((Join-Path $repoRoot "templates") + ";templates"),
    "--add-data", ((Join-Path $repoRoot "dados\bases_oficiais") + ";dados\bases_oficiais"),
    "--collect-all", "reportlab",
    "--hidden-import", "googleapiclient.discovery",
    "--hidden-import", "googleapiclient.errors",
    "--hidden-import", "google.auth.transport.requests",
    "--hidden-import", "google.oauth2.credentials",
    "--hidden-import", "google_auth_oauthlib.flow",
    (Join-Path $repoRoot "main.py")
)

& $venvPython @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller nao conseguiu gerar o executavel."
}

$exePath = Join-Path $distApp "FiscalPro.exe"
if (-not (Test-Path $exePath)) {
    throw "FiscalPro.exe nao foi criado em dist\FiscalPro."
}

Escrever-Etapa "Localizando Inno Setup 6"
$iscc = Localizar-Iscc
if (-not $iscc) {
    Write-Host ""
    Write-Host "O executavel do FiscalPro foi criado, mas o Inno Setup 6 nao esta instalado." -ForegroundColor Yellow
    Write-Host "Instale uma vez pelo Windows com este comando:" -ForegroundColor Yellow
    Write-Host "winget install --id JRSoftware.InnoSetup -e" -ForegroundColor White
    Write-Host ""
    Write-Host "Depois execute novamente CRIAR_INSTALADOR.bat." -ForegroundColor Yellow
    exit 3
}

$issPath = Join-Path $repoRoot "instalador\FiscalPro.iss"
if (-not (Test-Path $issPath)) {
    throw "Arquivo instalador\FiscalPro.iss nao encontrado."
}

$saidaDir = Join-Path $repoRoot "instalador\saida"
New-Item -ItemType Directory -Force -Path $saidaDir | Out-Null
$setupEsperado = Join-Path $saidaDir ("FiscalPro_Setup_" + $versao + ".exe")
if (Test-Path $setupEsperado) {
    Remove-Item $setupEsperado -Force
}

Escrever-Etapa "Gerando instalador FiscalPro Setup $versao"
& $iscc "/DMyAppVersion=$versao" "/DMyAppFileVersion=$versaoArquivo" $issPath
if ($LASTEXITCODE -ne 0) {
    throw "O Inno Setup nao conseguiu compilar o instalador."
}

if (-not (Test-Path $setupEsperado)) {
    throw "A compilacao terminou, mas o instalador esperado nao foi encontrado: $setupEsperado"
}

Escrever-Etapa "INSTALADOR CRIADO COM SUCESSO"
Write-Host "Arquivo:" -ForegroundColor Green
Write-Host $setupEsperado -ForegroundColor White
Write-Host ""
Write-Host "Versao: $versao" -ForegroundColor Green
Write-Host "O instalador preserva os dados do usuario em %LOCALAPPDATA%\FiscalPro." -ForegroundColor Green
