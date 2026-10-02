# Развёртывание WMS-сервера на боевом ПК

Целевая система: **Ubuntu Server 22.04 / 24.04** (или Debian 12), **PostgreSQL 16**, статический IP в локальной сети.

## Файлы этого каталога
| Файл | Назначение |
|---|---|
| `install_server.sh` | Полная установка: git clone → venv → зависимости → systemd → firewall |
| `setup_postgres.sh` | Создание роли `wms` и базы `wms` в PostgreSQL (запускать от пользователя postgres) |
| `wms.service` | Юнит systemd: автозапуск, перезапуск при падении, работа от пользователя `wms` |
| `wms.env.example` | Шаблон конфигурации `/etc/wms/wms.env` (строки подключения, секретный ключ) |

## Пошагово

### 0. Подготовка сервера
```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone Europe/Moscow
```
Здайте **статический IP** (netplan или в настройках роутера DHCP-резервацию), например `192.168.10.50`.

### 1. PostgreSQL 16
```bash
sudo apt install -y postgresql-16
sudo systemctl enable --now postgresql
```

### 2. Установка приложения
Перед запуском замените URL репозитория (или передайте переменной):
```bash
REPO_URL=https://github.com/ВАШ_ЛОГИН/wms-system.git sudo bash deploy/install_server.sh
```
Скрипт: клонирует код в `/opt/wms`, создаёт пользователя `wms`, python-venv, `/etc/wms/wms.env`
(секретный ключ генерируется автоматически), юнит `wms.service`, разрешает порт 8000 в ufw.

### 3. База данных
```bash
su postgres -c "bash /opt/wms/deploy/setup_postgres.sh"
```
Скрипт выведет сгенерированный пароль — скопируйте строку `WMS_DATABASE_URL=...`
в `/etc/wms/wms.env` (или задайте свой пароль через `WMS_DB_PASSWORD=...`).

### 4. Инициализация схемы и демо-данных
```bash
sudo -u wms mkdir -p /opt/wms/server/data && sudo -u wms chown wms:wms /opt/wms/server/data
sudo -u wms /opt/wms/venv/bin/python /opt/wms/server/scripts/init_db.py
```
Для «чистого» пересоздания: добавьте `--reset` (УДАЛИТ все данные!).
Скрипт создаёт схему и загружает демо-данные (пользователи, номенклатура, места хранения, коробки) —
они нужны для быстрой проверки системы; после проверки справочники правятся/удаляются через веб-интерфейс админа.

### 5. Запуск
```bash
sudo systemctl start wms
sudo systemctl status wms
journalctl -u wms -f            # живые логи uvicorn
```

### 6. Проверка
* Браузер контролёра: `http://192.168.10.50:8000/` → вход `admin/admin123` → **сразу сменить пароль**.
* API для ТСД: `curl http://192.168.10.50:8000/api/terminal/ping` → `{"ok":true}`.
* На каждом ТСД в приложении указать `http://192.168.10.50:8000`.

## Сопровождение

### Обновление кода
```bash
cd /opt/wms && sudo -u wms git pull
sudo /opt/wms/venv/bin/pip install -r server/requirements.txt
sudo systemctl restart wms
```

### Резервная копия БД (cron ежедневно)
```bash
# /etc/cron.daily/wms-backup
#!/bin/sh
pg_dump -U wms -h 127.0.0.1 wms | gzip > /var/backups/wms_$(date +%F).sql.gz
find /var/backups -name 'wms_*.sql.gz' -mtime +30 -delete
```
Пароль для pg_dump положите в `~postgres/.pgpass`: `127.0.0.1:5432:wms:wms:ПАРОЛЬ`.

### Безопасность (локальная сеть без интернета)
* Сервис работает от непривилегированного пользователя `wms`.
* `/etc/wms/wms.env` имеет права `600`.
* Порт 8000 открыт только для подсети Wi-Fi (ufw rule в install-скрипте — поправьте подсеть).
* HTTPS внутри своей сети обычно не требуется; если нужен — поставьте nginx + self-signed сертификат.

### Типовые проблемы
| Симптом | Решение |
|---|---|
| `connection refused` с ТСД | Проверьте IP/порт, `systemctl status wms`, правило ufw, что Wi-Fi и сервер в одной подсети |
| Ошибка аутентификации PostgreSQL | Пароль в `/etc/wms/wms.env` ≠ паролю роли; пересоздайте: `ALTER ROLE wms WITH PASSWORD '...'` |
| `psycopg2` не ставится | `sudo apt install build-essential python3-dev libpq-dev` и повторить п.2 |
| ТСД теряет связь | Приложение само переподключается каждые 5 с; проверьте удержание Wi-Fi на ТСД («не отключать при сне») |
| Нужен другой порт | `WMS_PORT` в `/etc/wms/wms.env` + правило ufw + адрес в приложении ТСД |
