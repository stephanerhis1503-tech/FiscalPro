#define MyAppName "FiscalPro Teste ST"
#define MyAppVersion "18.2.32-teste-st"
#define MyAppPublisher "Stephane Rhis"
#define MyAppExeName "FiscalPro_Teste_ST.exe"

[Setup]
AppId={{7C1E6832-5C38-4C71-9A20-2A73AE7EB1B4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoDescription=Instalador isolado para teste do motor ICMS-ST
VersionInfoProductName={#MyAppName}
DefaultDirName={localappdata}\Programs\FiscalPro Teste ST
DefaultGroupName=FiscalPro Teste ST
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=saida_teste_st
OutputBaseFilename=FiscalPro_Teste_ST_Setup
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
UsePreviousAppDir=yes
UsePreviousTasks=yes
SetupLogging=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: checkedonce

[Files]
Source: "..\dist_teste_st\FiscalPro_Teste_ST.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\FiscalPro Teste ST"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar FiscalPro Teste ST"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FiscalPro Teste ST"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir FiscalPro Teste ST"; Flags: nowait postinstall skipifsilent
