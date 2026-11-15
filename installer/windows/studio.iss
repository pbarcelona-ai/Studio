; Pistachio's Studio for Windows 10/11 (milestone MI, rule 12). Built by: python installer/build.py windows
; Per user (no admin rights), Start-menu and desktop shortcuts, an uninstaller that asks before removing projects.
; Installing over an older version keeps projects\, books\ and the saved settings (%USERPROFILE%\.pistachios_studio).
; The shortcuts run scripts\install_studio.py --launch on the bundled Python: the first time (and after an update) it shows the
; progress page that makes .venv; after that it starts the Studio straight away.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Stage
  #error Stage (the folder made by build.py) is required
#endif
#ifndef OutDir
  #define OutDir "dist"
#endif

[Setup]
AppId={{6B0F7C1E-3D2A-4C55-9E7B-5A1F2C9D8E41}
AppName=Pistachio's Studio
AppVersion={#AppVersion}
AppPublisher=Pistachio's Studio
DefaultDirName={localappdata}\Programs\Pistachios Studio
DefaultGroupName=Pistachio's Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutDir}
OutputBaseFilename=PistachiosStudio-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
UninstallDisplayName=Pistachio's Studio
#if FileExists(Stage + "\studio.ico")
SetupIconFile={#Stage}\studio.ico
UninstallDisplayIcon={app}\studio.ico
#endif
#ifdef SIGN
SignTool=studiosign
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a Pistachio's Studio shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pistachio's Studio"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\scripts\install_studio.py"" --launch"; WorkingDir: "{app}"; IconFilename: "{app}\studio.ico"
Name: "{group}\Uninstall Pistachio's Studio"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Pistachio's Studio"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\scripts\install_studio.py"" --launch"; WorkingDir: "{app}"; IconFilename: "{app}\studio.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\scripts\install_studio.py"" --launch"; WorkingDir: "{app}"; Description: "Finish setting up and open Pistachio's Studio"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; made after installing (by install_studio.py and the Studio), so the uninstaller would not know them otherwise
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\.venv.partial"
Type: filesandordirs; Name: "{app}\.install"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\scripts\__pycache__"
Type: filesandordirs; Name: "{app}\scripts\studio_app\__pycache__"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if DirExists(ExpandConstant('{app}\projects')) or DirExists(ExpandConstant('{app}\books')) then
    begin
      if MsgBox('Also delete your projects and books?' + #13#10 + #13#10 +
                'They are in ' + ExpandConstant('{app}') + '. Choose No to keep them (installing the Studio again finds them).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(ExpandConstant('{app}\projects'), True, True, True);
        DelTree(ExpandConstant('{app}\books'), True, True, True);
        DelTree(ExpandConstant('{app}\my_downloads'), True, True, True);
        DelTree(ExpandConstant('{app}'), True, True, True);
      end;
    end;
  end;
end;
