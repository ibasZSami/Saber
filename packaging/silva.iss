; Inno Setup script for Silva.
;
; This turns the PyInstaller output (dist/Silva/) into a real Windows
; installer: Silva-Setup.exe, with a Start Menu shortcut, an optional
; Desktop shortcut, and a proper uninstaller registered in "Apps & features".
;
; Requires Inno Setup (free, https://jrsoftware.org/isinfo.php) — a one-time
; download, not something this repo bundles. See packaging/README.md for the
; full build steps. Compile with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\silva.iss

#define MyAppName "Silva"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Silva"
#define MyAppExeName "Silva.exe"

[Setup]
AppId={{B4A6E7B4-9C2F-4E9A-8E8E-3F2C6E9E7A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Installs per-machine by default but doesn't require it — Silva writes its
; own config/data next to the exe, so a per-user folder works just as well
; if the user doesn't have admin rights.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Silva-Setup
SetupIconFile=silva.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
; No installer-level autostart task here on purpose: Silva manages its own
; autostart registration (Scheduled Task, falling back to a Run-key) from its
; own Settings screen once running — see src/core/autostart.py. A second,
; installer-owned Run-key entry would just be a duplicate that could launch
; Silva twice on logon.

[Files]
; The whole PyInstaller onedir output — exe + its _internal runtime + the
; bundled extracted_assets/plugins folders (see packaging/silva.spec).
Source: "..\dist\Silva\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Best-effort cleanup of user data created at runtime (config.json, memory
; DB, logs) so an uninstall doesn't leave orphaned files. Uses external
; deletion since these are created after install, outside [Files].
Type: filesandordirs; Name: "{app}\data"
Type: files; Name: "{app}\config.json"
