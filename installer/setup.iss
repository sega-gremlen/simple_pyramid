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
Source: "..\dist\simple_pyramid\*"; DestDir: "{app}"; Flags: recursesubdirs
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\Простая Пирамида"; Filename: "{app}\simple_pyramid.exe"
Name: "{group}\Простая Пирамида"; Filename: "{app}\simple_pyramid.exe"

[Run]
Filename: "{app}\simple_pyramid.exe"; Flags: postinstall nowait skipifsilent

[Code]
const
  WebView2ClientGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function IsWebView2Installed: Boolean;
var
  Version: string;
begin
  Result :=
    (RegQueryStringValue(HKLM64, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version) and (Version <> '')) or
    (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version) and (Version <> '')) or
    (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version) and (Version <> ''));
end;

procedure InstallWebView2;
var
  ResultCode: Integer;
begin
  SuppressibleMsgBox(
    'Для работы программы требуется компонент Microsoft Edge WebView2, который не найден в системе.' + #13#10 +
    'Сейчас начнётся его загрузка и установка — это может занять несколько минут в зависимости от скорости интернета.' + #13#10 +
    'Дождитесь завершения, не закрывайте окно установки.',
    mbInformation, MB_OK, IDOK);

  if not Exec(ExpandConstant('{app}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '',
    SW_SHOW, ewWaitUntilTerminated, ResultCode) then
  begin
    SuppressibleMsgBox(
      'Не удалось запустить установку WebView2. Установите его вручную позже, иначе программа может работать некорректно.',
      mbError, MB_OK, IDOK);
    Exit;
  end;

  if not IsWebView2Installed then
    SuppressibleMsgBox(
      'Установка WebView2 не завершилась успешно (возможно, отсутствует интернет-соединение).' + #13#10 +
      'Программа может работать некорректно, пока WebView2 не будет установлен вручную.',
      mbError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not IsWebView2Installed) then
    InstallWebView2;
end;