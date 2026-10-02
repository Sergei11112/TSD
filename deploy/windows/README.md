# Развёртывание WMS на Windows 10/11

Аналог `deploy/install_server.sh` для Linux. Работает на Windows 10 и 11,
процессоры x64 и ARM64 (включая Apple M1/M2 в Boot Camp / Parallels).
База данных по умолчанию — SQLite (`server/data/wms.db`), PostgreSQL опционален.

## Быстрая установка (2 шага)

1. **Установите Python 3.12**
   - Скачайте с https://www.python.org/downloads/windows/
     (для ARM64-ПК выбирайте «Windows ARM64 installer», для обычных — «Windows Installer (64-bit)»)
   - При установке **обязательно отметьте галочку `Add python.exe to PATH`**.

2. **Запустите установку**
   - Клонируйте или скачайте репозиторий, например в `C:\wms`:
     ```bat
     git clone https://github.com/Sergei11112/TSD.git C:\wms
     ```
     (если Git не установлен — скачайте ZIP с GitHub и распакуйте в `C:\wms`)
   - Двойной клик по **`C:\wms\deploy\windows\install.bat`**
     (лучше правой кнопкой → «Запуск от имени администратора», чтобы скрипт
     сразу открыл порт 8000 в брандмауэре для ТСД).

Скрипт сам: создаст виртуальное окружение `venv`, установит зависимости,
создаст базу с демо-данными, откроет порт в брандмауэре и создаст
`wms-start.bat` / `wms-stop.bat` в корне проекта + ярлыки в меню «Пуск» (папка WMS).

## Запуск и остановка

| Действие | Как |
|---|---|
| Запуск | двойной клик `wms-start.bat` (или Пуск → WMS → «запуск сервера») |
| Остановка | закрыть окно сервера или `wms-stop.bat` |
| Контролёр | http://localhost:8000 — вход `admin` / `admin123` |
| Экран ТСД в браузере | http://localhost:8000/terminal |
| IP для терминалов | печатается в окне при запуске (строки «адрес в сети») |

Сервер слушает `0.0.0.0:8000`, поэтому ТСД из локальной сети обращаются по адресу
`http://IP-компьютера:8000` (например `http://192.168.10.50:8000`).

## Автозапуск при включении компьютера (опционально)

Чтобы сервер поднимался сам без открытия окон (аналог systemd):

```bat
:: один раз, от администратора
C:\wms\deploy\windows\autostart_register.bat
```

- Лог пишется в `C:\wms\server\data\wms.log`
- Проверка/удаление: `schtasks /Query /TN "WMS Server"` / `schtasks /Delete /TN "WMS Server" /F`
- Ручной запуск задачи: `schtasks /Run /TN "WMS Server"`

## Обновление версии

```bat
cd C:\wms
git pull
deploy\windows\make_launchers.bat   :: пересоздать wms-start.bat с новыми путями
wms-stop.bat & wms-start.bat
```

Структура базы обновляется автоматически при старте; если нужна чистая БД —
удалите `server\data\wms.db` и выполните `venv\Scripts\python server\scripts\init_db.py`.

## Настройка статического IP (рекомендуется для работы с ТСД)

Параметры_IP-протокола_Интернет_версии_4 → «Использовать следующий IP-адрес»:
адрес (например `192.168.10.50`), маска `255.255.255.0`, шлюз роутера, DNS роутера.
Либо закрепите IP за этим ПК в DHCP-сервере роутера по MAC-адресу.

## Опционально: PostgreSQL вместо SQLite

1. Установите PostgreSQL 16 для Windows: https://www.postgresql.org/download/windows/
   (при установке задайте пароль пользователя `postgres`).
2. Создайте базу и роль (из `psql`):
   ```sql
   CREATE ROLE wms LOGIN PASSWORD 'ВАШ_ПАРОЛЬ';
   CREATE DATABASE wms OWNER wms;
   ```
3. Перед запуском задайте переменную окружения, например в `wms-start.bat`
   строкой перед `python run.py`:
   ```bat
   set WMS_DATABASE_URL=postgresql+psycopg2://wms:ВАШ_ПАРОЛЬ@127.0.0.1:5432/wms
   ```
4. Выполните инициализацию схемы: `venv\Scripts\python server\scripts\init_db.py`.

## Типовые проблемы

| Симптом | Решение |
|---|---|
| «Python не найден» | переустановите Python с галочкой *Add to PATH*, перезапустите install.bat |
| Окно запускается и сразу закрывается | запускайте install.bat из cmd, чтобы видеть ошибки; проверьте лог |
| Порт 8000 занят | `set WMS_PORT=8080` перед запуском, обновите адрес на ТСД |
| ТСД не видят сервер | правило брандмауэра (запуск install.bat от админа), тот же Wi-Fi-диапазон/подсеть, проверка с самого ПК: `http://localhost:8000` |
| Антивирус блокирует python.exe | добавьте `C:\wms\venv\Scripts\python.exe` в исключения |
| Нужен другой порт/IP наружу | переменные окружения `WMS_HOST`, `WMS_PORT`; секрет сессий — `WMS_SECRET_KEY` |

## Структура файлов здесь

```
deploy/windows/
├── install.bat              # полная установка (запустить один раз)
├── make_launchers.bat       # пересоздать wms-start/stop.bat и ярлыки (вызывается install.bat)
├── autostart_register.bat   # автозапуск через Планировщик задач (по желанию)
└── README.md                # эта инструкция
```
