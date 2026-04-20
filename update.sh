#!/bin/bash
# Скрипт обновления и перезапуска WebOnlineMonitor
# Update and restart script for WebOnlineMonitor
#
# Использование / Usage: ./update.sh [имя_сервиса / service_name]
# По умолчанию / Default service name: webmonitor

set -e

# Имя сервиса берётся из первого аргумента, иначе — значение по умолчанию
# Service name is taken from the first argument, otherwise the default is used
SERVICE="${1:-webmonitor}"

# Абсолютный путь к директории скрипта (директория приложения)
# Absolute path to the script's directory (application directory)
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# Путь к виртуальному окружению Python
# Path to the Python virtual environment
VENV="$APP_DIR/venv"

echo "==> Директория приложения / App directory: $APP_DIR"
echo "==> Сервис / Service: $SERVICE"
echo ""

# Проверяем, что systemd-сервис зарегистрирован в системе
# Check that the systemd service is registered in the system
if ! systemctl list-unit-files --type=service | grep -q "^${SERVICE}.service"; then
    echo "[WARN] Сервис '${SERVICE}.service' не найден в systemd. Перезапуск пропущен."
    echo "[WARN] Service '${SERVICE}.service' not found in systemd. Restart skipped."
    SKIP_RESTART=true
fi

# Получаем список новых коммитов из удалённого репозитория
# Fetch new commits from the remote repository
echo "==> Получение обновлений из git... / Fetching updates from git..."
export GIT_SSH_COMMAND='ssh -i ~/.ssh/webmonitor_deploy_key -o IdentitiesOnly=yes'
git -C "$APP_DIR" fetch origin

# Сравниваем локальный HEAD с удалённым, чтобы понять, есть ли обновления
# Compare local HEAD with remote to detect new changes
LOCAL=$(git -C "$APP_DIR" rev-parse HEAD)
REMOTE=$(git -C "$APP_DIR" rev-parse @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    # Локальная версия совпадает с удалённой — обновление не нужно
    # Local version matches remote — no update needed
    echo "    Уже актуальная версия. Обновление не требуется."
    echo "    Already up to date. No update needed."
else
    # Есть новые коммиты — применяем их через fast-forward merge
    # New commits found — apply them via fast-forward merge
    echo "    Найдены новые коммиты. Применяем обновления..."
    echo "    New commits found. Applying updates..."
    git -C "$APP_DIR" pull --ff-only
    echo "    Git pull выполнен успешно. / Git pull completed successfully."
fi

# Если есть файл зависимостей — обновляем пакеты
# If requirements.txt exists — update packages
if [ -f "$APP_DIR/requirements.txt" ]; then
    echo ""
    echo "==> Обновление зависимостей... / Updating dependencies..."

    if [ -d "$VENV" ]; then
        # Используем pip из виртуального окружения
        # Use pip from the virtual environment
        "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
    else
        # Виртуальное окружение не найдено — используем системный pip3
        # Virtual environment not found — fall back to system pip3
        pip3 install -q -r "$APP_DIR/requirements.txt"
    fi

    echo "    Зависимости обновлены. / Dependencies updated."
fi

# Перезапускаем сервис, если он зарегистрирован в systemd
# Restart the service if it is registered in systemd
if [ "${SKIP_RESTART}" != "true" ]; then
    echo ""
    echo "==> Перезапуск сервиса / Restarting service: ${SERVICE}..."
    systemctl restart "$SERVICE"
    sleep 2

    # Проверяем, что сервис успешно поднялся после перезапуска
    # Check that the service started successfully after restart
    if systemctl is-active --quiet "$SERVICE"; then
        echo "    Сервис запущен успешно. / Service started successfully."
    else
        # Сервис не запустился — выводим последние строки журнала и завершаем с ошибкой
        # Service failed to start — print recent journal output and exit with error
        echo "[ERROR] Сервис не запустился. / Service failed to start."
        echo "[ERROR] Вывод journalctl / journalctl output:"
        journalctl -u "$SERVICE" -n 30 --no-pager
        exit 1
    fi
fi

echo ""
echo "==> Готово. / Done."
