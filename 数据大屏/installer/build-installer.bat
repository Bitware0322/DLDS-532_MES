@echo off
rem ===========================================================================
rem  Build the DLDS-532 Windows installer (self-contained, no .NET on target).
rem  Usage: double-click, or run  installer\build-installer.bat
rem ===========================================================================
setlocal
cd /d "%~dp0.."

echo [1/3] Cleaning previous output...
if exist "dist\win-x64" rmdir /s /q "dist\win-x64"

echo [2/3] Publishing self-contained win-x64 build...
dotnet publish src\DLDS532.App\DLDS532.App.csproj -c Release -r win-x64 --self-contained true ^
    -m:1 -nodeReuse:false -p:UseSharedCompilation=false -o dist\win-x64
if errorlevel 1 goto :fail

echo [3/3] Compiling installer with Inno Setup...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo.
    echo Inno Setup 6 not found. Install it first:
    echo     winget install JRSoftware.InnoSetup
    goto :fail
)
"%ISCC%" installer\DLDS532.iss
if errorlevel 1 goto :fail

echo.
echo Build finished.
dir /b dist\DLDS532-*-setup.exe
goto :eof

:fail
echo.
echo BUILD FAILED
exit /b 1
