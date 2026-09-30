; OrdinFlow Inno Setup Script
; Enterprise-Grade Installer for Windows x64

#define MyAppName "OrdinFlow"
#define MyAppPublisher "Daniel Azanza Hartmann"
#define MyAppURL "https://github.com/DanAzanza/OrdinFlow"
#define MyAppExeName "Start_OrdinFlow.bat"
#ifndef MyAppVersion
  #define MyAppVersion "0.9.0"
#endif

[Setup]
AppId={{E68F9A42-120C-4E87-94BC-4E257F1DF012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=OrdinFlow-Setup-v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; 64-bit Windows enforcement
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; Dual-mode privilege strategy (lowest by default, dialog allows elevation)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Messages]
english.BeveledLabel=OrdinFlow Local AI Document & RPA Platform
german.BeveledLabel=OrdinFlow Lokale KI Dokumenten- & RPA-Plattform

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Root application launcher and manifests
Source: "..\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dashboard.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Start_OrdinFlow.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Install_OrdinFlow.bat"; DestDir: "{app}"; Flags: ignoreversion

; Core packages and web UI
Source: "..\core\*"; DestDir: "{app}\core"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\routes\*"; DestDir: "{app}\routes"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\settings\*"; DestDir: "{app}\settings"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\sample_data\*"; DestDir: "{app}\sample_data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Run environment setup during installation
Filename: "{cmd}"; Parameters: "/c """"{app}\Install_OrdinFlow.bat"""""; WorkingDir: "{app}"; StatusMsg: "Configuring OrdinFlow environment and hardware acceleration..."; Flags: runasoriginaluser waituntilterminated

; Post-install launch option (runasoriginaluser prevents UAC elevation poisoning)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallDelete]
Type: files; Name: "{app}\crash.log"
Type: files; Name: "{app}\main.log"
Type: filesandordirs; Name: "{app}\venv"

[Code]
// Pre-flight check: Verify that 64-bit Python is available on PATH
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  PythonFound: Boolean;
begin
  Result := True;
  PythonFound := Exec('where.exe', 'python', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
  if not PythonFound then
  begin
    if SuppressibleMsgBox(
      'Python 3.10, 3.11, or 3.12 (64-bit) was not detected on your system PATH.' + #13#10#13#10 +
      'OrdinFlow requires 64-bit Python with "Add Python to PATH" enabled.' + #13#10#13#10 +
      'Would you like to open https://www.python.org/downloads/ to install it now?',
      mbConfirmation, MB_YESNO, IDYES) = IDYES then
    begin
      ShellExec('open', 'https://www.python.org/downloads/', '', '', SW_SHOW, ewNoWait, ResultCode);
    end;
    Result := False;
    Exit;
  end;
end;

// Uninstallation safeguard: protect confidential cases, inbox, and settings
function InitializeUninstall(): Boolean;
var
  DataDir: String;
  CasesDir: String;
  PromptMsg: String;
begin
  Result := True;
  DataDir := ExpandConstant('{localappdata}\OrdinFlow');
  CasesDir := ExpandConstant('{app}\Cases');

  if DirExists(DataDir) or DirExists(CasesDir) then
  begin
    PromptMsg := 'Do you wish to retain your document database (Cases, Inbox, and settings)?' + #13#10#13#10 +
                 'Click YES to keep your documents and settings safe.' + #13#10 +
                 'Click NO to permanently delete all data.';
    if SuppressibleMsgBox(PromptMsg, mbConfirmation, MB_YESNO, IDYES) = IDNO then
    begin
      if DirExists(DataDir) then
        DelTree(DataDir, True, True, True);
      if DirExists(CasesDir) then
        DelTree(CasesDir, True, True, True);
      if DirExists(ExpandConstant('{app}\Inbox')) then
        DelTree(ExpandConstant('{app}\Inbox'), True, True, True);
      if DirExists(ExpandConstant('{app}\settings')) then
        DelTree(ExpandConstant('{app}\settings'), True, True, True);
    end;
  end;
end;
