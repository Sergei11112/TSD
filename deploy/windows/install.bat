@echo off
REM ============================================================
REM  WMS - установка сервера на Windows 10/11 (x64 / ARM64)
REM  Запускать двойным кликом или в cmd из папки deploy\windows
REM ============================================================
setlocal EnableExtensions
chcp 65001 >nul
title WMS: установка

cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "VENV=%ROOT%\venv"
set "VPY=%VENV%\Scripts\python.exe"

echo ============================================================
echo  Установка WMS-сервера
echo  Каталог проекта: %ROOT%
echo ============================================================
echo.

REM --- 1. Ищем Python 3.10+ -----------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ОШИБКА] Python не найден.
    echo Установите Python 3.12 с https://www.python.org/downloads/windows/
    echo ВАЖНО: при установке отметьте галочку "Add python.exe to PATH".
    echo После установки запустите этот скрипт снова.
    pause
    exit /b 1
)
echo [OK] Найден Python: %PY%
for /f "delims=" %%v in ('%PY% -c "import sys;print(sys.version.split()[0])"') do echo      версия %%v

REM --- 2. Виртуальное окружение --------------------------------
if not exist "%VPY%" (
    echo [..] Создаю виртуальное окружение venv...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv.
        pause
        exit /b 1
    )
) else (
    echo [OK] venv уже существует, пропускаю
)

REM --- 3. Зависимости ------------------------------------------
echo [..] Устанавливаю зависимости (fastapi, uvicorn, sqlalchemy)...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r "%ROOT%\server\requirements.txt"
if errorlevel 1 (
    echo [ОШИБКА] pip install не выполнился. Проверьте интернет-соединение.
    pause
    exit /b 1
)
echo [OK] Зависимости установлены

REM --- 4. База данных ------------------------------------------
if not exist "%ROOT%\server\data" mkdir "%ROOT%\server\data"
if exist "%ROOT%\server\data\wms.db" (
    echo [OK] База данных уже существует, НЕ трогаю её
    echo      ^(удалите server\data\wms.db для чистой инициализации^)
) else (
    echo [..] Инициализирую базу данных + демо-данные...
    pushd "%ROOT%\server"
    "%VPY%" scripts\init_db.py
    popd
    echo [OK] База создана: server\data\wms.db
)

REM --- 5. Правила брандмауэра (нужен запуск от администратора) --
echo.
echo [..] Пробую открыть порт 8000 в брандмауэре Windows (для ТСД)...
netsh advfirewall firewall show rule name="WMS HTTP 8000" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="WMS HTTP 8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1
    if errorlevel 1 (
        echo      [ВНИМАНИЕ] Нет прав администратора - порт 8000 НЕ открыт.
        echo      ТСД не увидят сервер. Откройте "Брандмауэр Windows" -^>
        echo      "Правила для входящих подключений" -^> создать правило
        echo      для TCP-порта 8000, ИЛИ запустите install.bat правой
        echo      кнопкой "Запуск от имени администратора".
    ) else (
        echo      [OK] Порт 8000 открыт для локальной сети
    )
) else (
    echo      [OK] Правило брандмауэра уже существует
)

REM --- 6. Создание .bat-файлов запуска -------------------------
call make_launchers.bat
echo [OK] Созданы: wms-start.bat, wms-stop.bat, ярлык в меню Пуск

echo.
echo ============================================================
echo  УСТАНОВКА ЗАВЕРШЕНА
echo  Запуск сервера: двойной клик по wms-start.bat
echo  (или меню Пуск - папка "WMS")
echo.
echo  После запуска:
echo    Контролер:   http://localhost:8000   (admin / admin123)
echo    Экран ТСД:   http://localhost:8000/terminal
echo  IP этого ПК для терминалов печатается в окне сервера
echo ============================================================
pause
endlocal
