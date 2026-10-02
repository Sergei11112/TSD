# Развёртывание WMS на macOS (Intel / Apple Silicon M1–M4)

Аналог `deploy/windows/install.bat` для macOS. База данных по умолчанию —
SQLite (`server/data/wms.db`), PostgreSQL опционален. Работает одинаково на
Mac с чипами M1/M2/M3/M4 и на Intel-Маках (все зависимости имеют нативные
пакеты для arm64 и x86_64).

## Быстрая установка (2 шага)

1. **Установите Python 3.12** (если ещё нет):
   - Через Homebrew (рекомендуется):
     ```bash
     brew install python@3.12
     ```
   - Или официальный установщик с https://www.python.org/downloads/macos/
     (для Apple Silicon качайте «macOS installer (Apple silicon)»).

2. **Запустите установку**:
   ```bash
   git clone https://github.com/Sergei11112/TSD.git ~/wms
   cd ~/wms
   bash deploy/macos/install.sh
   ```
   Либо скачайте ZIP с GitHub, распакуйте и дважды кликните
   `deploy/macos/install.command` (при первом запуске, если Gatekeeper
   ругается: правый клик → «Открыть»).

Скрипт сам: проверит Xcode Command Line Tools, создаст виртуальное окружение
`venv`, установит зависимости, создаст базу с демо-данными и файлы запуска
`wms-start.command` / `wms-stop.command` в корне проекта.

## Запуск и остановка

| Действие | Как |
|---|---|
| Запуск | двойной клик `wms-start.command` (откроется Терминал) |
| Остановка | закрыть окно сервера или двойной клик `wms-stop.command` |
| Контролёр | http://localhost:8000 — вход `admin` / `admin123` |
| Экран ТСД в браузере | http://localhost:8000/terminal |
| IP для терминалов | печатается в окне при запуске; также: Системные настройки → Wi-Fi |

Сервер слушает `0.0.0.0:8000`, поэтому ТСД из локальной сети обращаются по
адресу `http://IP-МАКА:8000` (например `http://192.168.10.50:8000`).

### Брандмауэр macOS
Если включён (Системные настройки → Сеть → Брандмауэр), при первом запуске
подтвердите разрешение входящих соединений для Python — иначе терминалы не
достанут до сервера.

## Автозапуск при входе в систему (опционально)

Создайте файл `~/Library/LaunchAgents/wur.studio.wms.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>wur.studio.wms</string>
  <key>ProgramArguments</key><array>
    <string>/Users/ВАШ_ЛОГИН/wms/venv/bin/python</string>
    <string>/Users/ВАШ_ЛОГИН/wms/server/run.py</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/ВАШ_ЛОГИН/wms/server</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/wms.log</string>
  <key>StandardErrorPath</key><string>/tmp/wms.err</string>
</dict></plist>
```

Активация: `launchctl load ~/Library/LaunchAgents/wur.studio.wms.plist`
(удаление: `launchctl unload …`). Логи: `/tmp/wms.log`.

## Обновление версии

```bash
cd ~/wms && git pull
./venv/bin/pip install -r server/requirements.txt
bash deploy/macos/install.sh   # пересоздаст wms-start.command
```

## Сборка приложения для ТСД (Android) на Маке

M1/M2/M3/M4 полностью подходят для Android Studio:
1. Установите Android Studio (arm64-сборка).
2. Откройте папку `tcd-android`, дождитесь загрузки Gradle.
3. Build → Build APK(s) — готовый APK появится в
   `tcd-android/app/build/outputs/apk/debug/`.
4. В настройках приложения на ТСД укажите `http://IP-МАКА:8000`.

## Типовые проблемы

| Симптом | Решение |
|---|---|
| «файл повреждён / неизвестный разработчик» на .command | правый клик → Открыть (один раз) |
| `xcrun: error: invalid active developer path` | `xcode-select --install` |
| порт 8000 занят | `lsof -i :8000`, остановить процесс или задать `WMS_PORT` |
| pip собирает пакет с ошибками компиляции | установлены ли Command Line Tools (см. выше) |
| ТСД не видят сервер | брандмауэр Mac, та же Wi-Fi сеть, пинг IP с терминала |
