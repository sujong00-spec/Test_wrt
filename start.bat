@echo off
chcp 65001 >nul
title 小学生默写助手服务
set "DISTRO=Ubuntu"

echo ============================================
echo   小学生默写助手 · 正在启动服务
echo   这个窗口不要关，关了浏览器就打不开了
echo ============================================
echo.

for /f "usebackq delims=" %%i in (`wsl.exe -d %DISTRO% -e wslpath -a "%CD%"`) do set "WSLDIR=%%i"
if "%WSLDIR%"=="" (
  echo 没能定位到 WSL 里的项目路径：请确认已装 WSL 与 %DISTRO% 发行版，
  echo 并把本文件放在项目目录下双击。
  pause
  exit /b 1
)

wsl.exe -d %DISTRO% -e bash -lc "cd '%WSLDIR%' && exec python3 server.py"
echo.
echo 服务已停止。
pause