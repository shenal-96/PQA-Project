; ─────────────────────────────────────────────────────────────────────────────
; PQA — Power Quality Analysis · Windows installer (Inno Setup 6.1+)
;
; Packages the PyInstaller onedir output (dist\PQA\) into a single Setup .exe and
; provisions the runtime the embedded WebView2/Edge-Chromium UI needs:
;
;   • WebView2 Evergreen Runtime — downloaded + silently installed if absent.
;     (Ships with Windows 11; may be missing on older Windows 10.)
;   • .NET Framework 4.8 — used by pythonnet because the app forces
;     PYTHONNET_RUNTIME=netfx (desktop/shell.py main()). 4.8 is built into
;     Windows 10 1903+/11, so we only *verify* it and warn if somehow absent —
;     we do NOT bundle/force the heavy modern .NET Desktop Runtime.
;
; Build (after building the web UI + app):
;   cd web && npm ci && npm run build && cd ..
;   pyinstaller desktop/pqa.spec --noconfirm
;   iscc desktop\installer.iss
; Output: desktop\Output\PQA-Setup-<version>.exe
;
; AppDir can be overridden:  iscc /DAppDir=path\to\PQA desktop\installer.iss
; ─────────────────────────────────────────────────────────────────────────────

#define AppName "PQA — Power Quality Analysis"
#define AppShortName "PQA"
#define AppVersion "0.1.0"
#define AppPublisher "PQA"
#define AppExe "PQA.exe"
#ifndef AppDir
  #define AppDir "..\dist\PQA"
#endif

[Setup]
; A stable AppId keeps upgrades/uninstall coherent across versions.
AppId={{B7E4B6B2-2C9E-4E3A-9C2D-6E1F5A0C9D11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppShortName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=Output
OutputBaseFilename=PQA-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Admin so the WebView2 runtime installs per-machine.
PrivilegesRequired=admin
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire PyInstaller onedir payload (PQA.exe + _internal\, incl. the bundled
; single-file web UI and python_calamine/matplotlib/docx).
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppShortName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppShortName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppShortName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppShortName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  { Evergreen WebView2 per-machine client key (x64 → WOW6432Node) and the
    Microsoft "fwlink" for the Evergreen Bootstrapper. }
  WV2_KEY_HKLM = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WV2_KEY_HKCU = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WV2_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';
  NET48_RELEASE = 528040;  { .NET Framework 4.8 minimum Release value }

function WebView2Installed(): Boolean;
var
  pv: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, WV2_KEY_HKLM, 'pv', pv) then
    Result := (pv <> '') and (pv <> '0.0.0.0');
  if not Result then
    if RegQueryStringValue(HKCU, WV2_KEY_HKCU, 'pv', pv) then
      Result := (pv <> '') and (pv <> '0.0.0.0');
end;

function Net48Installed(): Boolean;
var
  release: Cardinal;
begin
  Result := RegQueryDWordValue(HKLM,
    'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full', 'Release', release)
    and (release >= NET48_RELEASE);
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;  { keep going }
end;

{ PrepareToInstall runs after the user confirms, before files are copied — the
  right place to provision prerequisites. A failure here is non-fatal: WebView2
  may also be provided by an installed Edge browser, so we log and continue. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  setupExe: String;
  resultCode: Integer;
begin
  Result := '';

  if not WebView2Installed() then
  begin
    try
      DownloadTemporaryFile(WV2_URL, 'MicrosoftEdgeWebview2Setup.exe', '', @OnDownloadProgress);
      setupExe := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
      if not Exec(setupExe, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, resultCode) then
        Log('WebView2 bootstrapper failed to launch.')
      else
        Log('WebView2 bootstrapper exit code: ' + IntToStr(resultCode));
    except
      Log('WebView2 provisioning skipped (download/install error): ' + GetExceptionMessage);
    end;
  end;

  if not Net48Installed() then
    MsgBox('PQA needs Microsoft .NET Framework 4.8, which was not detected.'
      + #13#10 + 'It is included with Windows 10 (1903+) and Windows 11. If the '
      + 'app fails to start, install .NET Framework 4.8 from Microsoft and retry.',
      mbInformation, MB_OK);
end;
