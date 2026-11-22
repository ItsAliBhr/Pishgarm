; Inno Setup script — Persian installer, per-user install, desktop shortcut (doc 07 §7.4).
; Build: iscc /DAppVersion=0.1.0 tools\installer.iss   (after pyinstaller app.spec)

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6C1F3B2E-8D4A-4E7B-9C25-5A1F0D7E3B61}
AppName=دفتر اسناد پیشگرم
AppVersion={#AppVersion}
AppPublisher=پیشگرم سازان فولاد ایرانیان
DefaultDirName={autopf}\PishgarmDocs
DefaultGroupName=دفتر اسناد پیشگرم
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PishgarmDocsSetup
SetupIconFile=..\app\resources\icons\app.ico
UninstallDisplayIcon={app}\PishgarmDocs.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern

[Languages]
Name: "farsi"; MessagesFile: "compiler:Languages\Farsi.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\PishgarmDocs\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\دفتر اسناد پیشگرم"; Filename: "{app}\PishgarmDocs.exe"
Name: "{autodesktop}\دفتر اسناد پیشگرم"; Filename: "{app}\PishgarmDocs.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PishgarmDocs.exe"; Description: "{cm:LaunchProgram,دفتر اسناد پیشگرم}"; Flags: nowait postinstall skipifsilent

; User data lives in %LOCALAPPDATA%\PishgarmDocs and is deliberately NOT removed on uninstall.
