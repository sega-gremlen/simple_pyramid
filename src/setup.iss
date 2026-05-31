[Setup]
AppName=Простая Пирамида
AppVersion={#AppVersion}
DefaultDirName={localappdata}\SimplePyramid
PrivilegesRequired=lowest
OutputBaseFilename=simple_pyramid
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
SetupIconFile=favicon.ico

[Files]
Source: "simple_pyramid\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{userdesktop}\Простая Пирамида"; Filename: "{app}\simple_pyramid.exe"
Name: "{group}\Простая Пирамида"; Filename: "{app}\simple_pyramid.exe"

[Run]
Filename: "{app}\simple_pyramid.exe"; Flags: postinstall nowait skipifsilent