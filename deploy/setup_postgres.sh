#!/usr/bin/env bash
# Создание роли и базы wms в PostgreSQL. Запуск: sudo -u postgres bash setup_postgres.sh
# (нужны права: su postgres -c "bash /opt/wms/deploy/setup_postgres.sh")
set -euo pipefail

DB_PASS="${WMS_DB_PASSWORD:-$(openssl rand -hex 12)}"

sudo -u postgres psql <<SQL
-- роль и база создаются один раз; повторный запуск безопасен
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'wms') THEN
    CREATE ROLE wms LOGIN PASSWORD '${DB_PASS}';
  END IF;
END \$\$;

SELECT 'база wms уже есть' WHERE EXISTS (SELECT FROM pg_database WHERE datname='wms');
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='wms'" | grep -q 1; then
    sudo -u postgres createdb -O wms wms
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE wms TO wms;"
fi

echo ""
echo "Готово. Пароль пользователя wms: ${DB_PASS}"
echo "Впишите его в /etc/wms/wms.env:"
echo "  WMS_DATABASE_URL=postgresql+psycopg2://wms:${DB_PASS}@127.0.0.1:5432/wms"
