; Whisper 배치 전사 도구 - Inno Setup 설치 스크립트
; https://jrsoftware.org/isinfo.php 에서 Inno Setup 다운로드 후
; 이 파일을 열고 빌드하면 WhisperBatchTool_Setup.exe가 생성됩니다.

#define MyAppName "Whisper 배치 전사 도구"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Whisper Batch Tool"
#define MyAppURL "https://github.com/johneybi/whisper-batch-tool"
#define MyAppExeName "run.bat"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\WhisperBatchTool
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=WhisperBatchTool_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Whisper 배치 전사 도구 설치
WelcomeLabel2=오디오/비디오 파일을 자동으로 텍스트로 변환하는 도구입니다.%n%nOpenAI Whisper를 사용하여 한국어 음성을 인식합니다.%n%n설치를 계속하려면 [다음]을 클릭하세요.

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 생성"; GroupDescription: "추가 옵션:"

[Files]
Source: "batch_whisper_transcriber.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "install.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "run.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup_env.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Whisper 전사 도구 실행"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Comment: "Whisper 배치 전사 도구 실행"
Name: "{group}\환경 재설치"; Filename: "{app}\install.bat"; WorkingDir: "{app}"; Comment: "Python 환경 재설치"
Name: "{group}\사용 설명서"; Filename: "{app}\README.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Whisper 전사 도구"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "Whisper 배치 전사 도구 실행"

[Run]
Filename: "{app}\setup_env.bat"; Parameters: """{app}"""; WorkingDir: "{app}"; StatusMsg: "Python 환경 구성 중... (시간이 걸릴 수 있습니다)"; Flags: runhidden waituntilterminated
Filename: "{app}\run.bat"; Description: "지금 바로 전사 도구 실행"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\__pycache__"
