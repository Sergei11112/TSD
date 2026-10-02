# WMS — система управления складом

WMS-сервер (FastAPI + PostgreSQL) с веб-интерфейсом в стиле 1С:WMS и тонким клиентом для ТСД (Android).

## Структура
```
server/        — Python-сервер (FastAPI, SQLAlchemy 2.0, Jinja2)
tcd-android/   — тонкий клиент для ТСД (Kotlin, WebView + перехват сканера через Intent)
deploy/        — скрипты и конфиги развёртывания
```

## Быстрый старт (разработка, SQLite — БД не нужен)
```bash
cd server
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py          # схема + демо-данные
python run.py                      # http://localhost:8000
```
Вход: `admin / admin123` (PIN 0000), `controller / ctrl123`, `ivanov / work123`.

## Боевое развёртывание (Ubuntu 22.04/24.04, PostgreSQL 16) — см. deploy/README.md
```bash
sudo apt install -y postgresql-16
REPO_URL=https://github.com/ВАШ_ЛОГИН/wms-system.git sudo bash deploy/install_server.sh
su postgres -c "bash /opt/wms/deploy/setup_postgres.sh"   # создаёт роль+БД, печатает пароль
nano /etc/wms/wms.env                                      # вписать пароль
sudo -u wms /opt/wms/venv/bin/python /opt/wms/server/scripts/init_db.py
systemctl start wms
```
Веб-интерфейс: `http://СТАТИЧЕСКИЙ_IP:8000/`

## ТСД
1. Соберите APK: `cd tcd-android && ./gradlew assembleDebug` (Android Studio тоже подходит, minSdk 23).
2. Установите на ТСД, в «Настройках» укажите `http://IP_СЕРВЕРА:8000`.
3. Вход по PIN сотрудника; сканер перехватывается нативно (Intent), без камеры.

## Переменные окружения
| Переменная | Назначение | По умолчанию |
|---|---|---|
| `WMS_DATABASE_URL` | `postgresql+psycopg2://user:pass@host:5432/wms` | SQLite в `server/data/wms.db` |
| `WMS_SECRET_KEY` | подпись cookie-сессий (hex) | demo — заменить! |
| `WMS_HOST` / `WMS_PORT` | адрес прослушивания | `0.0.0.0` / `8000` |
