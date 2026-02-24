; ADT Framework Windows Installer Script
; Requires Inno Setup 6+

[Setup]
AppName=ADT Framework
AppVersion=0.1.0
AppPublisher=ADT Framework
AppPublisherURL=https://github.com/human86x/adt-framework
DefaultDirName={autopf}\ADT Framework
DefaultGroupName=ADT Framework
OutputBaseFilename=ADT_Framework_Setup_0.1.0
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Files]
; Operator Console
Source: "..\..\adt-console\src-tauri\target\release\adt-console.exe"; DestDir: "{app}"; Flags: ignoreversion

; DTTP Service
Source: "..\..\dist\adt_dttp_service\*"; DestDir: "{app}\dttp"; Flags: ignoreversion recursesubdirs createallsubdirs

; Operational Center
Source: "..\..\dist\adt_operational_center\*"; DestDir: "{app}\center"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ADT Operator Console"; Filename: "{app}\adt-console.exe"

Name: "{group}\ADT Operational Center"; Filename: "{app}\center\adt_operational_center.exe"
Name: "{group}\ADT DTTP Service"; Filename: "{app}\dttp\adt_dttp_service.exe"
Name: "{group}\Uninstall ADT Framework"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\dttp\adt_dttp_service.exe"; Description: "Start DTTP Service"; Flags: nowait postinstall skipifsilent
Filename: "{app}\center\adt_operational_center.exe"; Description: "Start Operational Center"; Flags: nowait postinstall skipifsilent
