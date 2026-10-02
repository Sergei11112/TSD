#!/usr/bin/env bash
# ============================================================
# Установка WMS-сервера на Ubuntu 22.04/24.04 (или Debian 12)
# Запуск от root:  sudo bash install_server.sh
# После установки PostgreSQL 16:  sudo -u postgres ./setup_postgres.sh
# ============================================================
set -euo pipefail

WMS_DIR=/opt/wms
REPO_URL="${REPO_URL:-https://github.com/ВАШ_ЛОГИН/wms-system.git}"   # <-- замените!
BRANCH="${BRANCH:-main}"

echo "==> 1. Системные пакеты"
apt-get update
apt-get install -y git python3-venv python3-pip curl ca-certificates \
    build-essential python3-dev libpq-dev postgresql-client

echo "==> 2. Пользователь и каталог приложения"
id -u wms &>/dev/null || useradd --system --home "$WMS_DIR" --shell /usr/sbin/nologin wms
mkdir -p "$WMS_DIR"

if [ -d "$WMS_DIR/.git" ]; then
    echo "==> Каталог уже существует, обновляю код (git pull)"
    git -C "$WMS_DIR" fetch origin && git -C "$WMS_DIR" reset --hard "origin/$BRANCH"
else
    echo "==> 3. Клонирование репозитория $REPO_URL"
    git clone --branch "$BRANCH" "$REPO_URL" "$WMS_DIR"
fi
chown -R wms:wms "$WMS_DIR"

echo "==> 4. Python-окружение"
python3 -m venv "$WMS_DIR/venv"
"$WMS_DIR/venv/bin/pip" install --upgrade pip
"$WMS_DIR/venv/bin/pip" install -r "$WMS_DIR/server/requirements.txt"

echo "==> 5. Конфигурация /etc/wms/wms.env"
mkdir -p /etc/wms
if [ ! -f /etc/wms/wms.env ]; then
    cp "$WMS_DIR/deploy/wms.env.example" /etc/wms/wms.env
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|заменить-на-сгенерированный-hex-64|$SECRET|" /etc/wms/wms.env
    chown wms:wms /etc/wms/wms.env
    chmod 600 /etc/wms/wms.env
    echo "    СОЗДАЙТЕ базу PostgreSQL (см. setup_postgres.sh) и впишите пароль в /etc/wms/wms.env!"
else
    echo "    /etc/wms/wms.env уже существует — не трогаю."
fi

echo "==> 6. systemd-сервис"
cp "$WMS_DIR/deploy/wms.service" /etc/systemd/system/wms.service
systemctl daemon-reload
systemctl enable wms

echo "==> 7. Firewall (порт 8000 для локальной сети)"
if command -v ufw &>/dev/null; then
    ufw allow from 192.168.0.0/16 to any port 8000 proto tcp comment 'WMS local net' || true
    echo "    Разрешите подсеть вашего Wi-Fi, если она другая (команда выше)."
fi

echo ""
echo "============================================================"
echo " БАЗОВАЯ УСТАНОВКА ГОТОВА. Дальнейшие шаги:"
echo "  1) Установите PostgreSQL 16 (если ещё нет):"
echo "       sudo apt install -y postgresql-16"
echo "  2) Создайте БД:"
echo "       cd $WMS_DIR/deploy && sudo -u postgres bash ../deploy/setup_postgres.sh"
echo "  3) Впишите пароль в /etc/wms/wms.env"
echo "  4) Инициализируйте схему и данные:"
echo "       sudo -u wms $WMS_DIR/venv/bin/python $WMS_DIR/server/scripts/init_db.py"
echo "  5) Запустите:"
echo "       systemctl start wms && systemctl status wms"
echo "  6) Веб-интерфейс:  http://СТАТИЧЕСКИЙ_IP_СЕРВЕРА:8000/"
echo "     (admin / admin123 — смените пароль сразу!)"
echo "  7) На ТСД в приложении укажите адрес:  http://СТАТИЧЕСКИЙ_IP_СЕРВЕРА:8000"
echo "============================================================"
