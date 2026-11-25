; ============================================================================
;  DLDS-532 工业网络智能控制与维护可视化系统 —— 安装程序脚本
;  编译器：Inno Setup 6.3+  用法：ISCC.exe installer\DLDS532.iss
;  前置：先执行 dotnet publish -c Release -r win-x64 --self-contained -o dist\win-x64
; ============================================================================

#define AppName        "DLDS-532 工业网络智能控制与维护可视化系统"
#define AppShortName   "DLDS-532"
#define AppVersion     "0.5.0"
#define AppPublisher   "DLDS-532 Project"
#define AppExeName     "DLDS532.exe"
#define BuildDir       "..\dist\win-x64"

[Setup]
; AppId 是升级/卸载的识别依据，一旦发布**不可再改**，否则会被当成另一个软件
AppId={{6F1B7C2A-7E64-4C3B-9A1E-3D5A0C8B4E21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppShortName}

; 默认装到 Program Files（提权时）或 用户目录\Programs（不提权时），向导第 2 步可自由修改
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppShortName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

; 默认不要求管理员：现场工控机往往拿不到管理员密码。
; 安装向导里会提供「为所有用户安装」选项，勾选后才提权。
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 目标程序是 win-x64 自包含，.NET 8 最低要求 Win10
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; 安装包体积：自包含产物约 160MB，用最大压缩
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename={#AppShortName}-{#AppVersion}-win-x64-setup
WizardStyle=modern
SetupLogging=yes
; 默认中文，不弹语言选择框（需要英文界面时用 /LANG=english 启动安装包）
ShowLanguageDialog=no

; 覆盖安装时若程序正在运行，让 Restart Manager 提示用户关闭
CloseApplications=yes
RestartApplications=no

UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
UninstallDisplaySize=170000000

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "创建开始菜单快捷方式(&S)"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart";     Description: "{cm:AutoStartProgram,{#AppShortName}}"; GroupDescription: "{cm:AutoStartProgramGroupDescription}"; Flags: unchecked

[Files]
; 自包含发布产物（含 config\db120.mapping.json），目标机无需安装 .NET 运行时
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; {group} = {autoprograms}\{#AppShortName}，即开始菜单里的独立文件夹
Name: "{group}\{#AppShortName}";        Filename: "{app}\{#AppExeName}"; Comment: "{#AppName}"; Tasks: startmenuicon
Name: "{group}\卸载 {#AppShortName}";   Filename: "{uninstallexe}";      Comment: "卸载 {#AppName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppShortName}";  Filename: "{app}\{#AppExeName}"; Comment: "{#AppName}"; Tasks: desktopicon

[Registry]
; HKA = 提权时写 HKLM、不提权时写 HKCU，两种安装模式都能正确记录
Root: HKA; Subkey: "Software\{#AppShortName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}";             Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#AppShortName}"; ValueType: string; ValueName: "Version";     ValueData: "{#AppVersion}";    Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#AppShortName}"; ValueType: string; ValueName: "DataDir";     ValueData: "{localappdata}\DLDS532"; Flags: uninsdeletekey

; 开机自启：仅在勾选「开机时自动启动」任务时写入，卸载时自动删除该值
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "{#AppShortName}"; ValueData: """{app}\{#AppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppShortName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 运行期数据（设置 + 事件日志），确保卸载后不留残余
Type: filesandordirs; Name: "{localappdata}\DLDS532"
Type: files;          Name: "{app}\*.log"
Type: dirifempty;     Name: "{app}"
