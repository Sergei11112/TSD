#!/bin/bash
# ============================================================
#  WMS — установка сервера на macOS (Intel / Apple Silicon M1-M4)
#  Запуск из терминала:  bash deploy/macos/install.sh
#  (или двойной клик по install.command)
# ============================================================
set -e

cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
VENV="$ROOT/venv"
VPY="$VENV/bin/python"

echo "============================================================"
echo " Установка WMS-сервера (macOS)"
echo " Каталог проекта: $ROOT"
echo "============================================================"
echo

# --- 0. Command Line Tools (нужны для сборки некоторых пакетов) ---
if command -v xcode-select >/dev/null 2>&1 && ! xcode-select -p >/dev/null 2>&1; then
    echo "[..] Установите Xcode Command Line Tools (появится окно):"
    xcode-select --install || true
    echo "     После завершения установки запустите этот скрипт снова."
    exit 1
fi

# --- 1. Ищем Python 3.10+ --------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
        VER="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
        MAJ="${VER%%.*}"; MIN="${VER##*.}"
        if [ "$MAJ" -ge 3 ] && [ "$MIN" -ge 10 ]; then PY="$c"; break; fi
    fi
done

if [ -z "$PY" ]; then
    echo "[ОШИБКА] Python 3.10+ не найден."
    echo "Варианты установки:"
    echo "  1) Homebrew (рекомендуется):"
    echo "       /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "       brew install python@3.12"
    echo "  2) Официальный установщик (выбирайте macOS arm64 для M1-M4):"
    echo "       https://www.python.org/downloads/macos/"
    echo "После установки запустите этот скрипт снова."
    exit 1
fi
echo "[OK] Найден Python: $PY ($($PY -c 'import sys;print(sys.version.split()[0])'))"

ARCH="$(uname -m)"
echo "[OK] Архитектура: $ARCH (Pillow/qrcode/psycopg2 имеют пакеты и для arm64, и для Intel)"

# --- 2. Виртуальное окружение ----------------------------------------
if [ ! -x "$VPY" ]; then
    echo "[..] Создаю виртуальное окружение venv..."
    "$PY" -m venv "$VENV"
else
    echo "[OK] venv уже существует, пропускаю"
fi

# --- 3. Зависимости -----------------------------------------------------
echo "[..] Устанавливаю зависимости (pip install)..."
"$VPY" -m pip install --upgrade pip -q
"$VPY" -m pip install -r server/requirements.txt

# --- 4. База данных (SQLite + демо-данные) ------------------------------
mkdir -p server/data
if [ -f server/data/wms.db ]; then
    echo "[OK] База уже существует: server/data/wms.db (не перезаписываю)"
    echo "     Пересоздать с нуля: $VPY server/scripts/init_db.py --reset"
else
    echo "[..] Создаю базу данных и демо-данные..."
    (cd server && "$VPY" scripts/init_db.py)
fi

# --- 5. Файлы запуска (.command открываются двойным кликом в Finder) ----
cat > "$ROOT/wms-start.command" <<EOF
#!/bin/bash
cd "$ROOT/server"
echo "============================================================"
echo " WMS сервер запущен:"
echo "   Контролёр : http://localhost:8000"
echo "   Экран ТСД : http://localhost:8000/terminal"
IP=\$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
[ -n "\$IP" ] && echo "   Для ТСД в сети: http://\$IP:8000"
echo " Остановка: Ctrl+C или wms-stop.command"
echo "============================================================"
exec "$VPY" run.py
EOF

cat > "$ROOT/wms-stop.command" <<EOF
#!/bin/bash
pkill -f "run.py" && echo "Сервер остановлен." || echo "Сервер не запущен."
EOF

chmod +x "$ROOT/wms-start.command" "$ROOT/wms-stop.command"

# Снимаем quarantine-атрибут, если проект скачан браузером
xattr -dr com.apple.quarantine "$ROOT" 2>/dev/null || true

echo
echo "============================================================"
echo " Установка завершена!"
echo
echo " ЗАПУСК:          двойной клик по wms-start.command"
echo "                  (или в терминале: ./wms-start.command)"
echo " ВХОД:            admin / admin123  -> http://localhost:8000"
echo " ЭКРАН ТСД:       http://localhost:8000/terminal"
echo " IP ДЛЯ ТЕРМИНАЛОВ: Системные настройки -> Wi-Fi -> IP-адрес"
echo
echo " Если macOS пишет «файл повреждён» при первом запуске .command:"
echo "   правый клик по файлу -> Открыть -> подтвердите."
echo
echo " Брандмауэр: если включен (Системные настройки -> Сеть -> Брандмауэр),"
echo " при первом запуске разрешите Python принимать входящие соединения,"
echo " иначе ТСД из локальной сети не достанут до сервера."
echo "============================================================"
