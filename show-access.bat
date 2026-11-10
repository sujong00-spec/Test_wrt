@echo off
chcp 65001 >nul
title 查看访问口令
set "DISTRO=Ubuntu"

echo 下面是打开本服务需要的口令与链接（不要把口令发给别人）。
echo.

for /f "usebackq delims=" %%i in (`wsl.exe -d %DISTRO% -e wslpath -a "%CD%"`) do set "WSLDIR=%%i"
if "%WSLDIR%"=="" (
  echo 没能定位到 WSL 里的项目路径。
  pause
  exit /b 1
)

wsl.exe -d %DISTRO% -e bash -lc "cd '%WSLDIR%' && python3 server.py --show-access"
echo.
pause