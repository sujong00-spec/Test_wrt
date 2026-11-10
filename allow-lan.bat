@echo off
chcp 65001 >nul
title 开放局域网访问（需要管理员）
set "PORT=8770"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 需要管理员权限，正在弹出授权窗口，请点「是」...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

echo 正在设置端口转发与防火墙（端口 %PORT%）...
netsh interface portproxy delete v4tov4 listenport=%PORT% listenaddress=0.0.0.0 >nul 2>&1
netsh interface portproxy add v4tov4 listenport=%PORT% listenaddress=0.0.0.0 connectport=%PORT% connectaddress=127.0.0.1
netsh advfirewall firewall delete rule name="小学生默写助手 %PORT%" >nul 2>&1
netsh advfirewall firewall add rule name="小学生默写助手 %PORT%" dir=in action=allow protocol=TCP localport=%PORT%

echo.
echo 设置完成。同一 Wi-Fi 下的手机 / 平板用浏览器打开：
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4" ^| findstr /r /c:"192\.168\." /c:"10\." /c:"172\."') do echo    http://%%i:%PORT%/
echo.
echo 打不开时依次检查：服务窗口有没有在跑、两台设备是不是同一个 Wi-Fi、电脑有没有开代理/VPN。
echo.
pause