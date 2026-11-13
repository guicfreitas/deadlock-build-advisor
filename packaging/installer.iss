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
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

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

[Code]
// One copy only. Inno upgrades in place when the scope matches, but a per-user and an
// all-users install are two registrations (HKCU vs HKLM): on 2026-11-12 an update in the
// wrong scope left 0.2.0 in G:\ and 0.2.1 in Program Files. Before installing, remove a
// copy registered in the other scope (an all-users copy needs admin: Windows asks).
const
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7C1E0B9A-5D7E-4C2B-9C1F-3E1D2B6A8F41}_is1';

procedure RemoveOtherScopeCopy();
var
  Root, Code: Integer;
  Cmd: String;
  Ok: Boolean;
begin
  if IsAdminInstallMode then Root := HKCU else Root := HKLM64;
  if not RegQueryStringValue(Root, UninstKey, 'UninstallString', Cmd) then Exit;
  Cmd := RemoveQuotes(Cmd);
  if not FileExists(Cmd) then Exit;
  Log('Removing the copy installed in the other scope: ' + Cmd);
  if Root = HKLM64 then
    Ok := ShellExec('runas', Cmd, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code)
  else
    Ok := Exec(Cmd, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if not Ok then Log('Could not remove it (code ' + IntToStr(Code) + ')');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then RemoveOtherScopeCopy();
end;
