#ifndef MyAppVersion
  #define MyAppVersion "18.2.32"
#endif
#ifndef MyAppFileVersion
  #define MyAppFileVersion "18.2.32.0"
#endif

#define MyAppName "FiscalPro"
#define MyAppPublisher "Stephane Rhis"
#define MyAppExeName "FiscalPro.exe"

[Setup]
AppId={{9AF10590-156C-4D78-996A-17E8AC396270}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=© 2026 Stephane Rhis
VersionInfoVersion={#MyAppFileVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Instalador do FiscalPro
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\FiscalPro
DefaultGroupName=FiscalPro
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=saida
OutputBaseFilename=FiscalPro_Setup_{#MyAppVersion}
SetupIconFile=..\assets\fiscalpro.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ChangesAssociations=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
SetupLogging=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: checkedonce

[Files]
Source: "..\dist\FiscalPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{localappdata}\FiscalPro"
Name: "{localappdata}\FiscalPro\dados"
Name: "{localappdata}\FiscalPro\dados\financeiro"
Name: "{localappdata}\FiscalPro\dados\seguranca"
Name: "{localappdata}\FiscalPro\dados\robo_email"
Name: "{localappdata}\FiscalPro\dados\entregas"
Name: "{localappdata}\FiscalPro\logs"
Name: "{localappdata}\FiscalPro\backups"

[Icons]
Name: "{group}\FiscalPro"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Dados do FiscalPro"; Filename: "{sys}\explorer.exe"; Parameters: "{localappdata}\FiscalPro"
Name: "{group}\Desinstalar FiscalPro"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FiscalPro"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o FiscalPro"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
