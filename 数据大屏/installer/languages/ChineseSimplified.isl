; DLDS-532 安装程序 —— 简体中文语言包
; Inno Setup 官方未内置简体中文，这里只覆盖向导流程中会出现的消息；
; 未列出的消息 Inno 会自动回退到英文默认值（不影响功能）。

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=936
DialogFontName=Microsoft YaHei UI
DialogFontSize=9

[Messages]

; *** 应用标题（含卸载程序标题）
SetupAppTitle=安装程序
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=卸载 %1

; *** 通用
InformationTitle=提示
ConfirmTitle=确认
ErrorTitle=错误

; *** 启动
SetupLdrStartupMessage=即将安装 %1。是否继续？
InvalidParameter=命令行参数无效：%n%n%1
SetupAlreadyRunning=安装程序已经在运行。
WindowsVersionNotSupported=本程序不支持当前版本的 Windows。
SetupFileMissing=安装目录中缺少文件 %1，请重新获取安装程序。
SetupFileCorrupt=安装文件已损坏，请重新获取安装程序。

; *** 运行中检测
SetupAppRunningError=安装程序检测到 %1 正在运行。%n%n请先关闭它，然后点击"确定"继续，或点击"取消"退出。
UninstallAppRunningError=卸载程序检测到 %1 正在运行。%n%n请先关闭它，然后点击"确定"继续，或点击"取消"退出。

; *** 退出确认
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。现在退出将不会安装本程序。%n%n你可以稍后重新运行安装程序完成安装。%n%n确定要退出吗？

; *** 按钮
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ButtonNewFolder=新建文件夹(&M)

; *** 欢迎页
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=本向导将引导你完成 [name/ver] 的安装。%n%n建议在继续之前关闭其他正在运行的应用程序。

; *** 选择安装位置
WizardSelectDir=选择安装位置
SelectDirDesc=[name] 应安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到下面的文件夹。
SelectDirBrowseLabel=点击"下一步"继续。如需安装到其他文件夹，请点击"浏览"。
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。

; *** 选择附加任务
WizardSelectTasks=选择附加任务
SelectTasksDesc=需要执行哪些附加任务？
SelectTasksLabel2=请选择安装 [name] 时需要一并完成的附加任务，然后点击"下一步"。

; *** 选择开始菜单文件夹
WizardSelectProgramGroup=选择开始菜单文件夹
SelectStartMenuFolderDesc=安装程序应把程序的快捷方式放在哪里？
SelectStartMenuFolderLabel3=安装程序将在下面的开始菜单文件夹中创建程序快捷方式。
SelectStartMenuFolderBrowseLabel=点击"下一步"继续。如需选择其他文件夹，请点击"浏览"。

; *** 准备安装
WizardReady=准备安装
ReadyLabel1=安装程序已准备好，即将开始安装 [name]。
ReadyLabel2a=点击"安装"开始安装；如需检查或修改设置，请点击"上一步"。
ReadyLabel2b=点击"安装"开始安装。
ReadyMemoDir=安装位置：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：

; *** 安装过程
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备安装 [name]。
WizardInstalling=正在安装
InstallingLabel=正在安装 [name]，请稍候。
StatusExtractFiles=正在解压文件...
StatusRollback=正在回滚更改...

; *** 完成页
FinishedHeadingLabel=[name] 安装向导完成
FinishedLabelNoIcons=[name] 已安装到你的计算机。
FinishedLabel=[name] 已安装到你的计算机，可通过已创建的快捷方式启动。
ClickFinish=点击"完成"退出安装程序。
FinishedRestartLabel=要完成 [name] 的安装，必须重启计算机。是否立即重启？
FinishedRestartMessage=要完成 [name] 的安装，必须重启计算机。%n%n是否立即重启？

; *** 卸载
WizardUninstalling=卸载状态
UninstallStatusLabel=正在从你的计算机中移除 %1，请稍候。
StatusUninstalling=正在卸载 %1...
ConfirmUninstall=确定要完全移除 %1 及其所有组件吗？
UninstallNotFound=文件"%1"不存在，无法卸载。
UninstallOpenError=无法打开文件"%1"，无法卸载。
UninstallOnlyOnWin64=本程序只能运行在 64 位 Windows 上。
UninstalledAll=%1 已成功从你的计算机中移除。
UninstalledMost=%1 卸载完成。%n%n部分内容未能移除，可手动删除。
UninstalledAndNeedsRestart=要完成 %1 的卸载，必须重启计算机。%n%n是否立即重启？

[CustomMessages]
NameAndVersion=%1 版本 %2
AdditionalIcons=附加快捷方式：
CreateDesktopIcon=创建桌面快捷方式(&D)
CreateQuickLaunchIcon=创建快速启动栏快捷方式(&Q)
UninstallProgram=卸载 %1
LaunchProgram=运行 %1
AutoStartProgramGroupDescription=启动选项：
AutoStartProgram=开机时自动启动 %1
AddonHostProgramNotFound=在所选文件夹中找不到 %1。%n%n仍要继续吗？
