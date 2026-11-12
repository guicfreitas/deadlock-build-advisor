; Inno Setup script for Deadlock Build Advisor. Built by packaging/build.ps1, which passes
; /DAppVersion=<version from deadlock_advisor/__init__.py>.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Deadlock Build Advisor"
#define AppExe "DeadlockBuildAdvisor.exe"

[Setup]
AppId={{7C1E0B9A-5D7E-4C2B-9C1F-3E1D2B6A8F41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Deadlock Build Advisor
AppPublisherURL=https://github.com/guicfreitas/deadlock-build-advisor
DefaultDirName={autopf}\DeadlockBuildAdvisor
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; per-user install by default: no admin prompt, updates don't need elevation
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=DeadlockBuildAdvisor-Setup-{#AppVersion}
SetupIconFile=icon.ico
; shown on the install wizard (skipped by the updater's /SILENT installs)
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; close a running copy before updating/uninstalling (it holds the .exe open)
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\DeadlockBuildAdvisor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; silent = the app's own updater ran us: reopen it (it already had its page open)
Filename: "{app}\{#AppExe}"; Parameters: "--restarted --no-browser"; Flags: nowait skipifnotsilent

[UninstallDelete]
; the API cache is safe to drop; settings in %APPDATA%\deadlock-advisor are kept on purpose
Type: filesandordirs; Name: "{localappdata}\deadlock-advisor\cache"
