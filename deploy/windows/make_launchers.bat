@echo off
REM Создает wms-start.bat / wms-stop.bat в корне проекта и ярлыки в меню Пуск.
REM Вызывается из install.bat; можно запускать и отдельно после git pull.
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0..\.."
set "ROOT=%CD%"

REM ---------- wms-start.bat ----------
> "%ROOT%\wms-start.bat" echo @echo off
>> "%ROOT%\wms-start.bat" echo title WMS - сервер управления складом
>> "%ROOT%\wms-start.bat" echo cd /d "%ROOT%\server"
>> "%ROOT%\wms-start.bat" echo echo ============================================================
>> "%ROOT%\wms-start.bat" echo echo  WMS-сервер запускается...
>> "%ROOT%\wms-start.bat" echo echo  Для остановки: закройте окно или wms-stop.bat
>> "%ROOT%\wms-start.bat" echo echo ============================================================
>> "%ROOT%\wms-start.bat" echo for /f "tokens=2 delims=:" %%a in ('ipconfig ^^^| findstr /c:"IPv4"') do echo    адрес в сети: %%a
>> "%ROOT%\wms-start.bat" echo start "" http://localhost:8000/login
>> "%ROOT%\wms-start.bat" echo "%ROOT%\venv\Scripts\python.exe" run.py
>> "%ROOT%\wms-start.bat" echo pause

REM ---------- wms-stop.bat ----------
> "%ROOT%\wms-stop.bat" echo @echo off
>> "%ROOT%\wms-stop.bat" echo powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" ^^^| Where-Object { $_.CommandLine -like '*run.py*' } ^^^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
>> "%ROOT%\wms-stop.bat" echo echo Сервер WMS остановлен (если был запущен).
>> "%ROOT%\wms-stop.bat" echo pause

REM ---------- Ярлыки в меню Пуск ----------
set "LNKDIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\WMS"
if not exist "%LNKDIR%" mkdir "%LNKDIR%"
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LNKDIR%\WMS - запуск сервера.lnk'); $s.TargetPath = '%ROOT%\wms-start.bat'; $s.WorkingDirectory = '%ROOT%'; $s.IconLocation = [Environment]::GetFolderPath('System') + '\SHELL32.dll,15'; $s.Description = 'Сервер WMS (http://localhost:8000)'; $s.Save(); $s2 = $ws.CreateShortcut('%LNKDIR%\WMS - остановка сервера.lnk'); $s2.TargetPath = '%ROOT%\wms-stop.bat'; $s2.WorkingDirectory = '%ROOT%'; $s2.IconLocation = [Environment]::GetFolderPath('System') + '\SHELL32.dll,132'; $s2.Save()"
if errorlevel 1 (
    echo [ВНИМАНИЕ] Не удалось создать ярлыки в меню Пуск - используйте wms-start.bat напрямую.
)
exit /b 0
