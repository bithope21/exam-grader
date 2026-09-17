; Build with Inno Setup after running build.py on Windows.
[Setup]
AppId=ExamGraderOffline
AppName=Exam Grader
AppVersion=1.0.3
DefaultDirName={localappdata}\Programs\ExamGrader
DefaultGroupName=Exam Grader
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Exam-Grader-v1.0.3-Windows-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\..\resources\icons\icon.ico
UninstallDisplayIcon={app}\ExamGrader.exe

[Files]
Source: "..\..\dist\ExamGrader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Exam Grader"; Filename: "{app}\ExamGrader.exe"; AppUserModelID: "bithope.examgrader.app"
Name: "{autodesktop}\Exam Grader"; Filename: "{app}\ExamGrader.exe"; Tasks: desktopicon; AppUserModelID: "bithope.examgrader.app"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

; Exam data lives in a separate app-data directory and is never removed here.
