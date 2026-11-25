@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 安装依赖 ===
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo === 生成图标资源 ===
python tools\make_assets.py
if errorlevel 1 goto :fail
echo === 打包 EXE ===
python -m PyInstaller DLDS532_OrderApp.spec --noconfirm --clean
if errorlevel 1 goto :fail
echo.
echo 打包完成： %~dp0dist\DLDS532_OrderApp.exe
pause
exit /b 0

:fail
echo.
echo 打包失败，请查看上面的错误信息。
pause
exit /b 1
