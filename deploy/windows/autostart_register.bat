@echo off
REM ============================================================
REM  WMS - автозапуск сервера при входе Windows + скрытие окна
REM  (аналог systemd-юнита на Linux). Запустить ОДИН РАЗ от
REM  администратора после install.bat.
REM ============================================================
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "VPY=%ROOT%\venv\Scripts\python.exe"

if not exist "%VPY%" (
    echo [ОШИБКА] Сначала выполните install.bat ^(venv не найден^)
    pause & exit /b 1
)

REM Планировщик: запуск при входе в систему, с наивысшими правами,
REM рабочий каталог server, stdout/stderr в лог-файл
schtasks /Create /F ^
  /TN "WMS Server" ^
  /TR "cmd /c cd /d \"%ROOT%\server\" && \"%VPY%\" run.py >> \"%ROOT%\server\data\wms.log\" 2>&1" ^
  /SC ONLOGON /RL HIGHEST >nul 2>&1

if errorlevel 1 (
    echo [ОШИБКА] Нет прав. Запустите autostart_register.bat
    echo          правой кнопкой "Запуск от имени администратора".
    pause & exit /b 1
)

REM Открываем порт 8000 для ТСД
netsh advfirewall firewall show rule name="WMS HTTP 8000" >nul 2>&1 || (
    netsh advfirewall firewall add rule name="WMS HTTP 8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1
)

echo [OK] Сервер WMS будет автоматически запускаться при входе в Windows.
echo      Лог: server\data\wms.log
echo      Удалить автозапуск: schtasks /Delete /TN "WMS Server" /F
echo      Быстрый старт сейчас: schtasks /Run /TN "WMS Server"
pause
endlocal
