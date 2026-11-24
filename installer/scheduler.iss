; Build the exe first (see README), then:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\scheduler.iss
; Output: installer\dist\Scheduler-Setup-<version>.exe

#define AppName "Scheduler"
#define AppVersion "0.1.0"

[Setup]
; Fixed id: lets a newer setup upgrade the installed app instead of adding a second copy.
AppId={{6F3C2A9E-4B1D-4E8A-9C57-2D8E1F0B7A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
; Per-user install: no admin prompt, goes to %LOCALAPPDATA%\Programs\Scheduler.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Scheduler-Setup-{#AppVersion}
SetupIconFile=..\backend\assets\scheduler.ico
UninstallDisplayIcon={app}\Scheduler.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\backend\dist\Scheduler.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Scheduler.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Scheduler.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Scheduler.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Uninstall leaves %APPDATA%\Scheduler (to-dos, mail summaries) in place on purpose.
