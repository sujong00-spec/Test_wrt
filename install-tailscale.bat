@echo off
chcp 65001 >nul
title 远程访问（Tailscale 私有网络，装一次就够）
set "PORT=8770"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在弹出授权窗口，请点「是」...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

set "TS=C:\Program Files\Tailscale\tailscale.exe"

if not exist "%TS%" (
  echo [1/3] 正在安装 Tailscale...
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi' -OutFile $env:TEMP\tailscale.msi; Start-Process msiexec -ArgumentList '/i',$env:TEMP\tailscale.msi,'/qn','/norestart' -Wait"
  timeout /t 8 /nobreak >nul
)

echo [2/3] 放行本机端口 %PORT%
netsh interface portproxy delete v4tov4 listenport=%PORT% listenaddress=0.0.0.0 >nul 2>&1
netsh interface portproxy add v4tov4 listenport=%PORT% listenaddress=0.0.0.0 connectport=%PORT% connectaddress=127.0.0.1
netsh advfirewall firewall delete rule name="小学生默写助手 %PORT%" >nul 2>&1
netsh advfirewall firewall add rule name="小学生默写助手 %PORT%" dir=in action=allow protocol=TCP localport=%PORT%

echo [3/3] 加入你的私有网络（会弹出浏览器，用你自己的账号登录一次）
"%TS%" up

echo.
echo ==========================================================
echo  这台电脑在私有网络里的地址：
"%TS%" ip -4
echo ==========================================================
echo.
echo 接着在 iPad / 手机上装 Tailscale 并用同一个账号登录，
echo 然后用浏览器打开  http://上面那个地址:%PORT%/
echo 装完之后在任何网络都能用，公网上没有任何入口。
echo.
pause